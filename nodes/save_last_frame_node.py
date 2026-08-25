"""Save Last Frame node for ComfyUI.

Persists the trailing frame(s) of a generation to a named slot on disk so a
later queue run can pick them up as the start image of the next shot. Built
for scene continuation with i2v models (Wan 2.2 and friends), where the only
way to extend a shot is to hand the model the frame you ended on.

Pipeline:  Wan i2v → Save Video (FFMPEGA)
                   ↘ images ↘ Save Last Frame (FFMPEGA)   [slot: "drone"]

           ...later run...
           Load Last Frame (FFMPEGA) [slot: "drone"] → Wan i2v start image

Connect ``images`` whenever you can: the tensor is written straight to PNG
with no h264 round-trip. Extracting from the encoded file instead bakes in
compression artifacts and yuv420p chroma subsampling, which compound
visibly over a chain of generations.
"""

import glob
import logging
import os
import shutil

import numpy as np
import torch

import folder_paths

try:
    from ..core.last_frame import (
        DEFAULT_PREFIX,
        DEFAULT_SLOT,
        MAX_TAIL_FRAMES,
        embed_workflow_png,
        extract_tail_frames,
        frame_name,
        probe_video_stats,
        sanitize_slot,
        select_tail_indices,
        slot_prefix,
    )
except ImportError:  # pragma: no cover - direct (non-package) import
    from core.last_frame import (  # type: ignore
        DEFAULT_PREFIX,
        DEFAULT_SLOT,
        MAX_TAIL_FRAMES,
        embed_workflow_png,
        extract_tail_frames,
        frame_name,
        probe_video_stats,
        sanitize_slot,
        select_tail_indices,
        slot_prefix,
    )

logger = logging.getLogger("FFMPEGA")

# Above this duration, decoding the whole video into RAM as a last resort
# stops being reasonable. Fine for an 81-frame Wan clip, catastrophic for a
# 10-minute 4K source.
_FULL_DECODE_MAX_SECONDS = 60.0


class SaveLastFrameNode:
    """Save the last frame(s) of a video or IMAGE batch to a named slot."""

    def __init__(self):
        self.output_dir = folder_paths.get_output_directory()
        self.type = "output"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "slot_name": ("STRING", {
                    "default": DEFAULT_SLOT,
                    "tooltip": (
                        "Named slot to write into "
                        "(output/ffmpega_last_frame/<slot>/). Load Last Frame "
                        "reads the same slot. Use different names to keep "
                        "several continuation chains apart, e.g. 'drone_a'. "
                        "Only letters, digits, - and _ are kept."
                    ),
                }),
                "frame_count": ("INT", {
                    "default": 1,
                    "min": 1,
                    "max": MAX_TAIL_FRAMES,
                    "step": 1,
                    "tooltip": (
                        "How many trailing frames to save. 1 is the usual "
                        "choice for i2v chaining; a few more is useful for "
                        "workflows that want several context frames."
                    ),
                }),
                "offset_from_end": ("INT", {
                    "default": 0,
                    "min": 0,
                    "max": 4096,
                    "step": 1,
                    "tooltip": (
                        "Skip this many frames at the very end. The literal "
                        "final frame is often the worst one — motion blur on "
                        "a moving shot, and i2v tails tend to soften. Try 1-3 "
                        "if the saved frame looks mushy."
                    ),
                }),
                "keep_history": ("BOOLEAN", {
                    "default": False,
                    "label_on": "Keep history",
                    "label_off": "Overwrite slot",
                    "tooltip": (
                        "Overwrite (default) keeps the slot at exactly "
                        "frame_count files with fixed names, so loading is "
                        "unambiguous. Keep history appends numbered files "
                        "instead, building an archive of every run."
                    ),
                }),
            },
            "optional": {
                "images": ("IMAGE", {
                    "tooltip": (
                        "Connect for lossless chaining — the tensor is "
                        "written straight to PNG with no h264 round-trip. "
                        "Takes priority over video_path when both are set."
                    ),
                }),
                "video_path": ("STRING", {
                    "forceInput": True,
                    "tooltip": (
                        "Fallback source: path to a video file whose tail "
                        "gets decoded with ffmpeg. Works with any video, but "
                        "inherits the file's compression artifacts."
                    ),
                }),
                "filename_prefix": ("STRING", {
                    "default": DEFAULT_PREFIX,
                    "tooltip": (
                        "Base filename inside the slot directory. "
                        "Files are written as <prefix>_00.png, _01.png, ..."
                    ),
                }),
            },
            "hidden": {
                "prompt": "PROMPT",
                "extra_pnginfo": "EXTRA_PNGINFO",
            },
        }

    RETURN_TYPES = ("IMAGE", "STRING", "STRING", "INT")
    RETURN_NAMES = ("last_frame", "frame_path", "slot_name", "frame_count")
    OUTPUT_TOOLTIPS = (
        "The saved frame(s), in chronological order. Wire this straight into "
        "the next generation for single-run chaining — it is the exact tensor "
        "that was written, so it avoids both the filesystem round-trip and "
        "PNG 8-bit quantisation.",
        "Absolute path of the newest saved frame.",
        "The sanitized slot name. Connect it to Load Last Frame's slot_name "
        "to force this node to run first when both live in one graph.",
        "How many frames were actually written (may be fewer than requested).",
    )
    FUNCTION = "save_last_frame"
    OUTPUT_NODE = True
    CATEGORY = "FFMPEGA"
    DESCRIPTION = (
        "Save the last frame(s) of a video or IMAGE batch into a named slot, "
        "so a later run can continue the scene from where it ended. Pair with "
        "Load Last Frame.\n\n"
        "For chaining inside a single workflow, use this node's last_frame "
        "output directly rather than adding a Load Last Frame node — two "
        "unconnected nodes have no guaranteed execution order, and the load "
        "side would read the previous run's frame."
    )

    # ── main ────────────────────────────────────────────────────────────

    def save_last_frame(
        self,
        slot_name: str = DEFAULT_SLOT,
        frame_count: int = 1,
        offset_from_end: int = 0,
        keep_history: bool = False,
        images=None,
        video_path: str = "",
        filename_prefix: str = DEFAULT_PREFIX,
        prompt=None,
        extra_pnginfo=None,
    ):
        slot = sanitize_slot(slot_name)
        frame_count = max(1, min(int(frame_count), MAX_TAIL_FRAMES))
        offset_from_end = max(0, int(offset_from_end))

        empty_result = (torch.zeros(1, 64, 64, 3), "", slot, 0)

        # --- Resolve the frames to write (tensor wins) ---
        frames, source = self._collect_frames(
            images, video_path, frame_count, offset_from_end,
        )
        if not frames:
            logger.warning(
                "SaveLastFrame: nothing to save for slot '%s' — leaving it "
                "untouched (connect images or video_path)", slot,
            )
            return {"ui": {"images": []}, "result": empty_result}

        logger.info(
            "SaveLastFrame: slot='%s' frames=%d source=%s",
            slot, len(frames), source,
        )

        # --- Resolve the slot directory ---
        try:
            full_output_folder, filename, _counter, subfolder, _ = (
                folder_paths.get_save_image_path(
                    slot_prefix(slot, filename_prefix), self.output_dir,
                )
            )
        except Exception as e:
            logger.error("SaveLastFrame: could not resolve slot path: %s", e)
            return {"ui": {"images": []}, "result": empty_result}

        os.makedirs(full_output_folder, exist_ok=True)

        # --- Write ---
        base_index = 0
        if keep_history:
            base_index = self._next_history_index(full_output_folder, filename)

        written: list[str] = []
        ui_images: list[dict] = []
        for i, frame in enumerate(frames):
            name = frame_name(base_index + i, filename)
            path = os.path.join(full_output_folder, name)
            try:
                self._write_png(frame, path)
            except Exception as e:
                logger.error("SaveLastFrame: failed writing %s: %s", name, e)
                continue
            embed_workflow_png(path, prompt, extra_pnginfo)
            written.append(path)
            ui_images.append({
                "filename": name, "subfolder": subfolder, "type": self.type,
            })

        if not written:
            return {"ui": {"images": []}, "result": empty_result}

        # Overwrite mode promises the slot holds exactly this run's files.
        # Without pruning, a run that saves 3 frames after one that saved 8
        # leaves _03.._07 behind and the load side returns a mix of both.
        if not keep_history:
            self._prune_slot(
                full_output_folder, filename, {os.path.basename(p) for p in written},
            )

        batch = torch.stack(frames, dim=0)
        return {
            "ui": {"images": ui_images},
            "result": (batch, written[-1], slot, len(written)),
        }

    # ── frame collection ────────────────────────────────────────────────

    def _collect_frames(
        self, images, video_path: str, frame_count: int, offset_from_end: int,
    ) -> tuple[list[torch.Tensor], str]:
        """Return ``(frames, source_label)``; frames are (H, W, 3) float32."""
        if images is not None:
            tensor = images if images.dim() == 4 else images.unsqueeze(0)
            indices = select_tail_indices(
                tensor.shape[0], frame_count, offset_from_end,
            )
            if indices:
                if offset_from_end >= tensor.shape[0]:
                    logger.warning(
                        "SaveLastFrame: offset_from_end=%d exceeds the %d-frame "
                        "batch — using the first frame",
                        offset_from_end, tensor.shape[0],
                    )
                return [tensor[i] for i in indices], "tensor (lossless)"
            logger.warning("SaveLastFrame: empty IMAGE batch")

        resolved = str(video_path or "").strip()
        if resolved:
            return self._frames_from_video(
                resolved, frame_count, offset_from_end,
            )

        return [], "none"

    def _frames_from_video(
        self, video_path: str, frame_count: int, offset_from_end: int,
    ) -> tuple[list[torch.Tensor], str]:
        """Pull trailing frames out of a video file via ffmpeg."""
        if not os.path.isfile(video_path):
            logger.warning("SaveLastFrame: video not found: %s", video_path)
            return [], "none"

        tmp_dir = None
        try:
            import tempfile
            tmp_dir = tempfile.mkdtemp(prefix="ffmpega_lastframe_")
            paths = extract_tail_frames(
                video_path, frame_count, offset_from_end, tmp_dir,
            )
            if paths:
                frames = []
                for p in paths:
                    try:
                        frames.append(self._read_png(p))
                    except Exception as e:
                        logger.warning("SaveLastFrame: unreadable frame %s: %s", p, e)
                if frames:
                    return frames, "ffmpeg (re-encoded source)"
        finally:
            if tmp_dir:
                shutil.rmtree(tmp_dir, ignore_errors=True)

        # Last resort: decode the whole clip. Gated on duration because
        # frames_to_tensor pulls every frame into RAM at once.
        _fps, duration, _nb = probe_video_stats(video_path)
        if 0 < duration <= _FULL_DECODE_MAX_SECONDS:
            try:
                try:
                    from ..core.media_converter import MediaConverter
                except ImportError:  # pragma: no cover
                    from core.media_converter import MediaConverter  # type: ignore
                tensor = MediaConverter().frames_to_tensor(video_path)
                indices = select_tail_indices(
                    tensor.shape[0], frame_count, offset_from_end,
                )
                if indices:
                    return [tensor[i] for i in indices], "ffmpeg (full decode)"
            except Exception as e:
                logger.warning("SaveLastFrame: full decode failed: %s", e)

        return [], "none"

    # ── file helpers ────────────────────────────────────────────────────

    @staticmethod
    def _write_png(frame: torch.Tensor, path: str) -> None:
        """Write an (H, W, 3) float tensor as PNG."""
        from PIL import Image

        arr = np.clip(frame.cpu().numpy() * 255.0, 0, 255).astype(np.uint8)
        Image.fromarray(arr).save(path, compress_level=4)

    @staticmethod
    def _read_png(path: str) -> torch.Tensor:
        """Read an image file as an (H, W, 3) float32 tensor in [0, 1]."""
        from PIL import Image

        img = Image.open(path).convert("RGB")
        arr = np.array(img).astype(np.float32) / 255.0
        return torch.from_numpy(arr)

    @staticmethod
    def _next_history_index(folder: str, filename: str) -> int:
        """Highest existing ``<filename>_NN`` index in the slot, plus one."""
        highest = -1
        for path in glob.glob(os.path.join(folder, f"{filename}_*")):
            base = os.path.splitext(os.path.basename(path))[0]
            parts = base.rsplit("_", 1)
            if len(parts) == 2 and parts[1].isdigit():
                highest = max(highest, int(parts[1]))
        return highest + 1

    @staticmethod
    def _prune_slot(folder: str, filename: str, keep: set[str]) -> None:
        """Delete stale ``<filename>_*`` files left by an earlier, longer run."""
        for path in glob.glob(os.path.join(folder, f"{filename}_*")):
            if os.path.basename(path) not in keep:
                try:
                    os.remove(path)
                except OSError as e:
                    logger.debug("SaveLastFrame: could not prune %s: %s", path, e)
