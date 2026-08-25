"""Load Last Frame node for ComfyUI.

Reads the frame(s) written by Save Last Frame from a named slot, so a new
queue run can continue a scene from where the previous one ended.

Discovery is deliberately *not* "newest image anywhere wins": the slot
directory is derived from the slot name, and files inside it carry fixed
zero-padded names, so the pairing is an explicit contract rather than an
mtime race against everything else in the output folder.
"""

from __future__ import annotations

import hashlib
import logging
import os

import torch
import torch.nn.functional as F

from .discovery.filesystem import SUPPORTED_EXTENSIONS, FilesystemScanner

try:
    from ..core.image_resize import (
        resize_image_tensor,
        resize_input_types as _resize_input_types,
    )
except ImportError:  # pragma: no cover - fallback for non-package import
    from core.image_resize import (  # type: ignore
        resize_image_tensor,
        resize_input_types as _resize_input_types,
    )

try:
    from ..core.last_frame import (
        DEFAULT_SLOT,
        LAST_FRAME_ROOT,
        MAX_TAIL_FRAMES,
        sanitize_slot,
        select_tail_indices,
        slot_dir,
    )
except ImportError:  # pragma: no cover
    from core.last_frame import (  # type: ignore
        DEFAULT_SLOT,
        LAST_FRAME_ROOT,
        MAX_TAIL_FRAMES,
        sanitize_slot,
        select_tail_indices,
        slot_dir,
    )

logger = logging.getLogger(__name__)


def _resolve_scan_dirs(source: str) -> list[str]:
    from .discovery.path_utils import resolve_scan_dirs
    return resolve_scan_dirs(source)


def _slot_view_entries(slot: str, prefix: str = "") -> list[dict]:
    """Describe a slot's frames for ComfyUI's ``/view`` endpoint.

    Returns ``[{filename, subfolder, type, mtime}, ...]`` oldest first. Slot
    files always live under the output directory, so the subfolder is derived
    rather than probed.
    """
    directory = slot_dir(slot)
    if not directory or not os.path.isdir(directory):
        return []

    subfolder = f"{LAST_FRAME_ROOT}/{sanitize_slot(slot)}"
    return [
        {
            "filename": os.path.basename(path),
            "subfolder": subfolder,
            "type": "output",
            "mtime": mtime,
        }
        for path, mtime, _size in _slot_entries(directory, prefix)
    ]


# ─── API routes ─────────────────────────────────────────────────────────
# Let both nodes show what a slot holds without queueing a prompt — placing
# the node is enough. Mirrors the /loadlast/latest_image contract.

try:
    from aiohttp import web
    from server import PromptServer

    @PromptServer.instance.routes.get("/ffmpega/last_frame/slot")
    async def _api_slot_frames(request):
        slot = request.query.get("slot", DEFAULT_SLOT)
        prefix = request.query.get("prefix", "")
        try:
            frames = _slot_view_entries(slot, prefix)
        except Exception as e:
            logger.warning("[LoadLastFrame] slot listing failed: %s", e)
            return web.json_response({"found": False, "frames": []})

        return web.json_response({
            "found": bool(frames),
            "slot": sanitize_slot(slot),
            "frames": frames,
            # Cheap change-detector so the client can skip re-rendering.
            "signature": "|".join(
                f"{f['filename']}:{f['mtime']}" for f in frames
            ),
        })

except Exception:  # pragma: no cover - no server (tests, headless import)
    pass


def _slot_entries(directory: str, prefix: str = "") -> list[tuple[str, float, int]]:
    """Return ``(path, mtime, size)`` for image files directly in ``directory``.

    Not recursive — a slot is flat by construction, and recursing would let
    an unrelated nested folder leak into the batch.
    """
    entries: list[tuple[str, float, int]] = []
    try:
        for entry in os.scandir(directory):
            try:
                if not entry.is_file(follow_symlinks=False):
                    continue
                if os.path.splitext(entry.name)[1].lower() not in SUPPORTED_EXTENSIONS:
                    continue
                if prefix and not entry.name.startswith(prefix):
                    continue
                stat = entry.stat()
                if stat.st_size == 0:
                    continue
                entries.append((entry.path, stat.st_mtime, stat.st_size))
            except OSError:
                continue
    except (OSError, PermissionError):
        return []
    # Filename order, not mtime: names are zero-padded and chronological,
    # whereas mtimes within one save can tie on coarse filesystems.
    entries.sort(key=lambda e: os.path.basename(e[0]))
    return entries


class LoadLastFrame:
    """Load the frame(s) previously saved into a named slot."""

    CATEGORY = "FFMPEGA"
    FUNCTION = "load"
    OUTPUT_NODE = True

    RETURN_TYPES = ("IMAGE", "MASK", "STRING", "INT", "INT", "INT")
    RETURN_NAMES = ("images", "mask", "image_path", "width", "height", "frame_count")
    OUTPUT_TOOLTIPS = (
        "The saved frame(s), oldest first. Feed the last one into an i2v "
        "model to continue the scene.",
        "Solid white mask matching the loaded frames.",
        "Absolute path of the newest loaded frame.",
        "Width of the loaded frames.",
        "Height of the loaded frames.",
        "How many frames were loaded. 0 means the slot was empty.",
    )
    DESCRIPTION = (
        "Load the frame(s) Save Last Frame wrote to a named slot, for "
        "continuing a scene in a later queue run.\n\n"
        "Within a single workflow, prefer Save Last Frame's last_frame output "
        "instead: unconnected nodes have no guaranteed execution order, and "
        "node caching is decided before execution starts, so this node would "
        "read the previous run's frame. Wire something into 'trigger' to at "
        "least force the ordering."
    )

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "slot_name": ("STRING", {
                    "default": DEFAULT_SLOT,
                    "tooltip": (
                        "Slot to read from — must match the slot_name on "
                        "Save Last Frame."
                    ),
                }),
                "refresh_mode": (["auto", "manual"], {
                    "default": "auto",
                    "tooltip": (
                        "auto: reload whenever the slot's contents change. "
                        "manual: only re-run when an input changes."
                    ),
                }),
                "frame_count": ("INT", {
                    "default": 1,
                    "min": 1,
                    "max": MAX_TAIL_FRAMES,
                    "step": 1,
                    "tooltip": (
                        "How many of the slot's trailing frames to load. "
                        "Capped at whatever the slot actually holds."
                    ),
                }),
                "offset_from_end": ("INT", {
                    "default": 0,
                    "min": 0,
                    "max": MAX_TAIL_FRAMES,
                    "step": 1,
                    "tooltip": (
                        "Skip this many frames at the end of the slot. Only "
                        "useful when the slot holds several frames."
                    ),
                }),
            },
            "optional": {
                "on_missing": (["fallback", "empty", "error"], {
                    "default": "fallback",
                    "tooltip": (
                        "What to do when the slot is empty — which is always "
                        "the case on the first run of a chain. fallback: use "
                        "the fallback_image input (a black frame if none is "
                        "connected). empty: return a black frame. error: stop "
                        "the run with a clear message."
                    ),
                }),
                "fallback_image": ("IMAGE", {
                    "tooltip": (
                        "Used when the slot is empty. Wire your original "
                        "start image here so run 1 and run N of a chain are "
                        "the same graph with no rewiring."
                    ),
                }),
                "source_folder": ("STRING", {
                    "default": "",
                    "tooltip": (
                        "Read from an arbitrary folder instead of the slot. "
                        "Files are picked by modification time here, since "
                        "the naming convention can't be assumed."
                    ),
                }),
                "filename_filter": ("STRING", {
                    "default": "",
                    "tooltip": "Only consider files starting with this prefix.",
                }),
                "mask": ("MASK", {
                    "tooltip": (
                        "Optional upstream MASK pass-through. When connected, "
                        "this mask is forwarded instead of the generated one."
                    ),
                }),
                "trigger": ("*", {
                    "tooltip": (
                        "Ordering hint. Wire any Save Last Frame output in to "
                        "force that node to run first. The value is ignored. "
                        "Note this fixes ordering but not caching — a freshly "
                        "written frame may still need a re-queue."
                    ),
                }),
                **_resize_input_types(),
            },
            "hidden": {
                "unique_id": "UNIQUE_ID",
            },
        }

    @classmethod
    def IS_CHANGED(cls, slot_name=DEFAULT_SLOT, refresh_mode="auto", **kwargs):
        """Hash the slot's contents so the node re-runs on a new save."""
        if refresh_mode == "manual":
            return ""

        directory = cls._resolve_dir(slot_name, kwargs.get("source_folder", ""))
        if not directory or not os.path.isdir(directory):
            # Cold slot: a constant keeps the scheduler from re-running this
            # node on every poll while the chain hasn't started yet.
            return ""

        m = hashlib.sha256()
        for path, mtime, size in _slot_entries(
            directory, kwargs.get("filename_filter", ""),
        ):
            m.update(f"{os.path.basename(path)}|{mtime}|{size}".encode())
        # Size matters here in a way it doesn't for LoadLastImage: in
        # overwrite mode the filename never changes, so name+mtime alone can
        # collide on a same-second rewrite of a same-sized frame.
        m.update(str(kwargs.get("frame_count", 1)).encode())
        m.update(str(kwargs.get("offset_from_end", 0)).encode())
        return m.hexdigest()

    @staticmethod
    def _resolve_dir(slot_name: str, source_folder: str) -> str:
        """Slot directory, or the first resolved scan dir when overridden."""
        if source_folder and source_folder.strip():
            dirs = _resolve_scan_dirs(source_folder.strip())
            return dirs[0] if dirs else ""
        return slot_dir(slot_name)

    # ── main ────────────────────────────────────────────────────────────

    def load(
        self,
        slot_name: str = DEFAULT_SLOT,
        refresh_mode: str = "auto",
        frame_count: int = 1,
        offset_from_end: int = 0,
        on_missing: str = "fallback",
        fallback_image=None,
        source_folder: str = "",
        filename_filter: str = "",
        mask=None,
        trigger=None,
        unique_id: str = "",
        enable_resize: bool = False,
        resize_width: int = 512,
        resize_height: int = 512,
        upscale_method: str = "nearest-exact",
        keep_proportion: str = "resize",
        pad_color: str = "0, 0, 0",
        crop_position: str = "center",
        divisible_by: int = 2,
        resize_device: str = "cpu",
    ):
        slot = sanitize_slot(slot_name)
        frame_count = max(1, min(int(frame_count), MAX_TAIL_FRAMES))
        offset_from_end = max(0, int(offset_from_end))

        def _finish(batch, path, count, preview):
            h, w = batch.shape[1], batch.shape[2]
            msk = mask if mask is not None else torch.ones(
                batch.shape[0], h, w, dtype=torch.float32,
            )
            if enable_resize:
                try:
                    batch, msk, w, h = resize_image_tensor(
                        batch,
                        width=resize_width,
                        height=resize_height,
                        keep_proportion=keep_proportion,
                        upscale_method=upscale_method,
                        divisible_by=divisible_by,
                        pad_color=pad_color,
                        crop_position=crop_position,
                        device=resize_device,
                        mask=msk,
                    )
                    logger.info("[LoadLastFrame] resized to %dx%d", w, h)
                except Exception as exc:
                    logger.warning("[LoadLastFrame] resize failed: %s", exc)
            return {
                "ui": {"images": preview},
                "result": (batch, msk, path, w, h, count),
            }

        # --- Gather candidate files ---
        directory = self._resolve_dir(slot, source_folder)
        paths = self._gather(
            directory, source_folder, filename_filter, frame_count, offset_from_end,
        )

        if not paths:
            return self._handle_missing(slot, on_missing, fallback_image, _finish)

        # --- Load ---
        scanner = FilesystemScanner()
        frames: list[torch.Tensor] = []
        loaded: list[str] = []
        for path in paths:
            try:
                tensor, _meta = scanner.load_image(path)
                frames.append(tensor)
                loaded.append(path)
            except Exception:
                logger.warning("[LoadLastFrame] Skipping unreadable: %s", path)

        if not frames:
            return self._handle_missing(slot, on_missing, fallback_image, _finish)

        # Conform to the first frame's dimensions so torch.stack succeeds.
        target_h, target_w = frames[0].shape[0], frames[0].shape[1]
        conformed = []
        for img in frames:
            if img.shape[0] != target_h or img.shape[1] != target_w:
                nchw = img.permute(2, 0, 1).unsqueeze(0)
                nchw = F.interpolate(
                    nchw, size=(target_h, target_w),
                    mode="bilinear", align_corners=False,
                )
                img = nchw.squeeze(0).permute(1, 2, 0)
            conformed.append(img)

        batch = torch.stack(conformed, dim=0)
        preview = self._preview_info(loaded)

        logger.info(
            "[LoadLastFrame] slot='%s' loaded %d frame(s) | %dx%d | %s",
            slot, len(conformed), target_w, target_h, loaded[-1],
        )
        return _finish(batch, loaded[-1], len(conformed), preview)

    # ── helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def _gather(
        directory: str,
        source_folder: str,
        filename_filter: str,
        frame_count: int,
        offset_from_end: int,
    ) -> list[str]:
        """Return the chosen file paths, oldest first."""
        if source_folder and source_folder.strip():
            # Arbitrary folder: naming is unknown, so mtime is the only
            # signal. FilesystemScanner returns newest-first — reverse it,
            # because a batch feeding a video model must be chronological.
            scan_dirs = _resolve_scan_dirs(source_folder.strip())
            newest_first = FilesystemScanner().scan(
                scan_dirs,
                n=frame_count + offset_from_end,
                filename_filter=filename_filter,
            )
            if not newest_first:
                return []
            ordered = list(reversed(newest_first))
        else:
            if not directory or not os.path.isdir(directory):
                return []
            ordered = [p for p, _m, _s in _slot_entries(directory, filename_filter)]
            if not ordered:
                return []

        indices = select_tail_indices(len(ordered), frame_count, offset_from_end)
        return [ordered[i] for i in indices]

    @staticmethod
    def _preview_info(paths: list[str]) -> list[dict]:
        """Build ``{"ui": {"images": ...}}` entries for the loaded files."""
        from .load_last_image import _resolve_view_info

        preview = []
        for path in paths:
            try:
                info = _resolve_view_info(path, os.path.dirname(path))
            except Exception:
                info = None
            if info:
                preview.append(info)
        return preview

    @staticmethod
    def _handle_missing(slot: str, on_missing: str, fallback_image, finish):
        """Cold slot: error, fall back to a supplied image, or return black."""
        if on_missing == "error":
            raise RuntimeError(
                f"LoadLastFrame: slot '{slot}' is empty. Run Save Last Frame "
                f"first, or set on_missing to 'fallback'."
            )

        if on_missing == "fallback" and fallback_image is not None:
            batch = (
                fallback_image if fallback_image.dim() == 4
                else fallback_image.unsqueeze(0)
            )
            logger.info(
                "[LoadLastFrame] slot '%s' empty — using fallback_image", slot,
            )
            return finish(batch, "", batch.shape[0], [])

        logger.warning(
            "[LoadLastFrame] slot '%s' is empty — returning a black frame. "
            "Connect fallback_image to start a chain cleanly.", slot,
        )
        return finish(torch.zeros(1, 512, 512, 3), "", 0, [])
