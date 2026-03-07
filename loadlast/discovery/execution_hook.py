"""
Execution hook for intercepting IMAGE outputs from ComfyUI's execution pipeline.

Hooks into PromptServer's send_sync to capture 'executed' events that contain
image data, and maintains an in-memory cache of recent image tensors.
"""

from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from threading import Lock
from typing import Optional

import torch

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """A single cached image from execution history."""
    tensor: torch.Tensor            # [H, W, 3] single image
    timestamp: float                # time.time() when captured
    source_node_id: str             # ComfyUI node ID that produced this image
    iteration: int                  # monotonic counter
    pixel_hash: int = 0             # lightweight perceptual hash for dedup
    metadata: dict = field(default_factory=dict)  # extracted metadata if available


class ImageExecutionCache:
    """
    Singleton cache that captures IMAGE outputs from ComfyUI executions.

    Strategy: Monkey-patch PromptServer.send_sync to intercept 'executed' events.
    When an 'executed' event fires, we increment the iteration counter so
    LoadLastImage can detect that new images are available.

    Image discovery itself is handled by FilesystemScanner (mtime-based).
    This cache additionally stores tensors pushed explicitly via push()
    for the pin/lock feature.
    """

    _instance: Optional[ImageExecutionCache] = None
    _lock = Lock()

    def __init__(self, max_history: int = 100):
        self._image_history: deque[CacheEntry] = deque(maxlen=max_history)
        self._max_history = max_history
        self._iteration_counter = 0
        self._last_prompt_id: Optional[str] = None  # Track per-execution increments
        self._last_increment_time: float = float("-inf")  # For prompt_id-less fallback grouping
        self._data_lock = Lock()

    @classmethod
    def get_instance(cls, max_history: int = 100) -> ImageExecutionCache:
        """Thread-safe singleton accessor."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls(max_history)
        return cls._instance

    @classmethod
    def setup(cls, prompt_server) -> ImageExecutionCache:
        """
        Register the execution hook with PromptServer.

        Wraps send_sync to intercept 'executed' events and track which
        images were produced during execution.
        """
        instance = cls.get_instance()

        original_send_sync = prompt_server.send_sync

        def hooked_send_sync(event, data, sid=None):
            if event == "executed":
                instance._on_executed(data)
            original_send_sync(event, data, sid)

        prompt_server.send_sync = hooked_send_sync
        logger.info("[LoadLast] Execution hook registered with PromptServer")
        return instance

    def _on_executed(self, data: dict):
        """
        Called when a node finishes execution.

        Increments the iteration counter so LoadLastImage can detect new
        images via IS_CHANGED. Only increments once per unique prompt_id,
        so workflows with multiple SaveImage nodes don't over-count.

        Note on iteration counter: This method and push() both increment
        _iteration_counter. Both share the counter so the monotonic ordering
        stays consistent regardless of discovery source. Only entries created
        by push() are retrievable via get_pinned().
        """
        try:
            output = data.get("output")
            if not output:
                return

            node_id = data.get("node", "unknown")
            prompt_id = data.get("prompt_id", "")
            images = output.get("images", [])
            if not images:
                return

            with self._data_lock:
                # Only increment counter once per execution (new prompt_id)
                if prompt_id and prompt_id != self._last_prompt_id:
                    self._iteration_counter += 1
                    self._last_prompt_id = prompt_id
                elif not prompt_id:
                    # Fallback: no prompt_id available. Use a 1-second window
                    # to group rapid 'executed' events from the same workflow,
                    # preventing multi-SaveImage workflows from over-counting.
                    now = time.monotonic()
                    if now - self._last_increment_time > 1.0:
                        self._iteration_counter += 1
                    self._last_increment_time = now

            logger.debug(
                "[LoadLast] Execution event from node %s (iteration %d)",
                node_id, self._iteration_counter
            )
        except Exception:
            logger.debug("[LoadLast] Error processing executed event", exc_info=True)

    def push(self, tensor: torch.Tensor, node_id: str = "manual",
             metadata: dict | None = None) -> CacheEntry:
        """
        Manually push an image tensor into the cache.

        Args:
            tensor: [H, W, 3] float32 image tensor in [0, 1] range
            node_id: source node ID
            metadata: optional metadata dict

        Returns:
            The created CacheEntry
        """
        from ..processing.dedup import compute_pixel_hash

        with self._data_lock:
            self._iteration_counter += 1
            entry = CacheEntry(
                tensor=tensor,
                timestamp=time.time(),
                source_node_id=node_id,
                iteration=self._iteration_counter,
                pixel_hash=compute_pixel_hash(tensor),
                metadata=metadata or {},
            )
            self._image_history.appendleft(entry)
            return entry

    def get_last_n(self, n: int, skip_dupes: bool = False) -> list[CacheEntry]:
        """
        Return the last N cache entries, newest first.

        Args:
            n: number of entries to return
            skip_dupes: if True, skip entries with duplicate pixel hashes
        """
        with self._data_lock:
            if not skip_dupes:
                return list(self._image_history)[:n]

            result = []
            seen_hashes = set()
            for entry in self._image_history:
                if entry.pixel_hash not in seen_hashes:
                    seen_hashes.add(entry.pixel_hash)
                    result.append(entry)
                    if len(result) >= n:
                        break
            return result

    def get_pinned(self, pin_index: int) -> Optional[CacheEntry]:
        """Return the cache entry at the given iteration index, or None."""
        if pin_index <= 0:
            return None
        with self._data_lock:
            for entry in self._image_history:
                if entry.iteration == pin_index:
                    return entry
            return None

    @property
    def iteration_counter(self) -> int:
        """Current iteration count."""
        return self._iteration_counter

    def clear(self):
        """Clear all cached data."""
        with self._data_lock:
            self._image_history.clear()
            self._iteration_counter = 0
            self._last_prompt_id = None
            self._last_increment_time = float("-inf")
