"""
Load Last Image node for ComfyUI.

Automatically loads the most recently created image(s) from ComfyUI's
output or temp directories, with an inline preview that loads immediately
(no queue needed) and a browser strip showing recent images.

Architecture mirrors LoadLastVideo:
  - Python registers /loadlast/latest_image and /loadlast/image_list API routes
  - JS polls those routes to show the latest image on the node
  - On execution, images are loaded via FilesystemScanner
  - Edit state (crop, resize, etc.) applied server-side via PIL
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import time

import numpy as np
import torch
import torch.nn.functional as F

try:
    import folder_paths
except ImportError:
    folder_paths = None  # type: ignore[assignment]

from .discovery.filesystem import FilesystemScanner, SUPPORTED_EXTENSIONS
from .discovery.execution_hook import ImageExecutionCache

logger = logging.getLogger(__name__)

# Maximum file size (bytes) to copy into temp for preview (200 MB)
_MAX_COPY_SIZE = 200 * 1024 * 1024

# Maximum values for integer parameters
BIGMAX = 2**31 - 1

# ─── User Image Selections (server-side state) ──────────────────────────
# Stores the user's explicit image selection from the browser strip,
# keyed by node ID.  Set via POST /loadlast/select_image, consumed
# (one-shot) by load().  Capped to prevent unbounded growth.
_user_image_selections: dict[str, dict] = {}

# ─── User Edit States (server-side state) ────────────────────────────
# Stores the user's inline edit state (crop, resize, etc.) from the
# Apply Edits button, keyed by node ID.  Consumed one-shot by load().
_user_edit_states: dict[str, dict] = {}

# Max entries for server-side state dicts
_MAX_SERVER_STATE_ENTRIES = 100

# TTL (seconds) for server-side state entries
_SERVER_STATE_TTL = 300  # 5 minutes

# Rate-limit TTL eviction scans
_EVICTION_SCAN_INTERVAL = 30
_last_eviction_scan_time: float = 0.0

# Cleanup timestamps
_last_preview_cleanup_time: float = 0.0
_STALE_PREVIEW_TTL = 60


def _capped_insert(d: dict, key: str, value: dict) -> None:
    """Insert value under key, evicting oldest entry if at cap."""
    if len(d) >= _MAX_SERVER_STATE_ENTRIES and key not in d:
        oldest = next(iter(d))
        d.pop(oldest, None)
    d[key] = value


# Allowed keys for image selection entries
_ALLOWED_ENTRY_KEYS = {"filename", "subfolder", "type"}
_ALLOWED_SEL_TYPES = {"output", "temp"}

# Allowed keys for inline edit state entries
_ALLOWED_EDIT_KEYS = {
    "crop_rect", "resize", "rotation", "flip",
    "padding", "brightness", "contrast", "saturation",
    "captions", "overlays",
}


# ─── API Routes ─────────────────────────────────────────────────────────

try:
    from aiohttp import web
    from server import PromptServer

    @PromptServer.instance.routes.get("/loadlast/latest_image")
    async def _api_latest_image(request):
        """Find the most recently modified image in output/temp."""
        source = request.query.get("source", "")
        prefix = request.query.get("prefix", "")

        scan_dirs = _resolve_scan_dirs(source)
        result = _find_latest_image_info(scan_dirs, prefix)
        if result is None:
            return web.json_response({"found": False})

        return web.json_response({"found": True, **result})

    @PromptServer.instance.routes.get("/loadlast/image_list")
    async def _api_image_list(request):
        """Return list of all recent images, sorted newest first."""
        source = request.query.get("source", "")
        prefix = request.query.get("prefix", "")
        try:
            limit = min(int(request.query.get("limit", "20")), 50)
        except (ValueError, TypeError):
            limit = 20

        scan_dirs = _resolve_scan_dirs(source)
        images = _find_all_images(scan_dirs, prefix, limit)
        return web.json_response({"images": images})

    @PromptServer.instance.routes.post("/loadlast/select_image")
    async def _api_select_image(request):
        """Store the user's image selection for a specific node."""
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "invalid JSON"}, status=400)

        node_id = str(body.get("node_id", ""))
        entry = body.get("entry")  # null to clear

        if not node_id:
            return web.json_response({"error": "node_id required"}, status=400)

        if entry:
            entry = {k: str(v) for k, v in entry.items() if k in _ALLOWED_ENTRY_KEYS}
            if not entry.get("filename"):
                return web.json_response({"error": "filename required"}, status=400)
            _capped_insert(
                _user_image_selections, node_id,
                {"data": entry, "ts": time.time()},
            )
            logger.info(
                "[LoadLastImage] Selection stored for node %s: %s",
                node_id, entry.get("filename", "?"),
            )
        else:
            _user_image_selections.pop(node_id, None)
            logger.debug("[LoadLastImage] Selection cleared for node %s", node_id)

        return web.json_response({"ok": True})

    @PromptServer.instance.routes.post("/loadlast/apply_image_edits")
    async def _api_apply_image_edits(request):
        """Store the user's inline image edit state for a specific node."""
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "invalid JSON"}, status=400)

        node_id = str(body.get("node_id", ""))
        if not node_id:
            return web.json_response({"error": "node_id required"}, status=400)

        edits = body.get("edits")  # null to clear
        if edits:
            edits = {k: v for k, v in edits.items() if k in _ALLOWED_EDIT_KEYS}
            _capped_insert(
                _user_edit_states, node_id,
                {"data": edits, "ts": time.time()},
            )
            logger.info("[LoadLastImage] Edit state stored for node %s", node_id)
        else:
            _user_edit_states.pop(node_id, None)
            logger.debug("[LoadLastImage] Edit state cleared for node %s", node_id)

        return web.json_response({"ok": True})

except (ImportError, AttributeError):
    # Running outside ComfyUI (e.g. pytest) — skip route registration
    pass


# ─── Image Discovery Helpers ────────────────────────────────────────────

def _resolve_scan_dirs(source: str) -> list[str]:
    """Return scan directories for a user-supplied source path."""
    from .discovery.path_utils import resolve_scan_dirs
    return resolve_scan_dirs(source)


def _is_path_sandboxed(path: str) -> bool:
    """Check if a path is within ComfyUI's allowed directories."""
    from .discovery.path_utils import is_path_sandboxed
    return is_path_sandboxed(path)


def _find_latest_image_info(directories: list[str], prefix: str = "") -> dict | None:
    """Find latest image and return {filename, subfolder, type, mtime}."""
    all_entries = _scan_image_entries(directories, prefix)
    if not all_entries:
        return None
    all_entries.sort(key=lambda x: x[2], reverse=True)
    info = _resolve_view_info(*all_entries[0][:2])
    if info:
        info["mtime"] = all_entries[0][2]
    return info


def _find_all_images(
    directories: list[str], prefix: str = "", limit: int = 20,
) -> list[dict]:
    """Find all recent images, sorted newest first, up to limit."""
    all_entries = _scan_image_entries(directories, prefix)
    all_entries.sort(key=lambda x: x[2], reverse=True)
    results = []
    for full_path, parent_dir, mtime in all_entries[:limit]:
        info = _resolve_view_info(full_path, parent_dir)
        if info:
            info["mtime"] = mtime
            results.append(info)
    return results


def _scan_image_entries(
    directories: list[str], prefix: str = "",
) -> list[tuple]:
    """Scan directories recursively for image files.

    Returns [(full_path, parent_dir, mtime), ...].
    """
    entries: list[tuple] = []
    for dir_path in directories:
        if not os.path.isdir(dir_path):
            continue
        _scan_image_dir(dir_path, prefix, entries)
    return entries


def _scan_image_dir(
    directory: str, prefix: str, entries: list[tuple], max_depth: int = 5,
) -> None:
    """Recursively collect image files from a directory."""
    if max_depth <= 0:
        return
    try:
        for entry in os.scandir(directory):
            try:
                if entry.is_file(follow_symlinks=False):
                    ext = os.path.splitext(entry.name)[1].lower()
                    if ext not in SUPPORTED_EXTENSIONS:
                        continue
                    if prefix and not entry.name.startswith(prefix):
                        continue
                    try:
                        mtime = entry.stat().st_mtime
                    except OSError:
                        continue
                    entries.append((os.path.realpath(entry.path), directory, mtime))
                elif entry.is_dir(follow_symlinks=False):
                    _scan_image_dir(entry.path, prefix, entries, max_depth - 1)
            except (PermissionError, OSError):
                continue
    except PermissionError:
        pass


def _resolve_view_info(full_path: str, parent_dir: str) -> dict | None:
    """Resolve an image file to {filename, subfolder, type} for /view."""
    if folder_paths is None:
        return None
    output_dir = folder_paths.get_output_directory()
    temp_dir = folder_paths.get_temp_directory()
    filename = os.path.basename(full_path)

    real_output = os.path.realpath(output_dir)
    real_temp = os.path.realpath(temp_dir)
    real_parent = os.path.realpath(parent_dir)

    is_output = real_parent == real_output or real_parent.startswith(real_output + os.sep)
    is_temp = real_parent == real_temp or real_parent.startswith(real_temp + os.sep)

    if is_output:
        subfolder = os.path.relpath(parent_dir, output_dir)
        view_type = "output"
    elif is_temp:
        subfolder = os.path.relpath(parent_dir, temp_dir)
        view_type = "temp"
    else:
        # Outside output/temp — copy to temp for preview
        try:
            file_size = os.path.getsize(full_path)
        except OSError:
            file_size = 0
        if file_size > _MAX_COPY_SIZE:
            logger.warning(
                "[LoadLastImage] Skipping copy of %s (%.0f MB exceeds cap)",
                filename, file_size / 1024 / 1024,
            )
            return None
        preview_dir = os.path.join(temp_dir, "loadlast_img_previews")
        os.makedirs(preview_dir, exist_ok=True)

        # TTL-based cleanup of stale preview copies
        global _last_preview_cleanup_time
        now = time.time()
        if now - _last_preview_cleanup_time > _STALE_PREVIEW_TTL:
            _last_preview_cleanup_time = now
            try:
                with os.scandir(preview_dir) as it:
                    for entry in it:
                        try:
                            if entry.stat().st_mtime < now - _STALE_PREVIEW_TTL:
                                os.remove(entry.path)
                        except OSError:
                            pass
            except OSError:
                pass

        path_hash = hashlib.sha256(full_path.encode()).hexdigest()[:12]
        safe_name = f"{path_hash}_{filename}"
        dest = os.path.join(preview_dir, safe_name)
        if not os.path.exists(dest) or os.path.getmtime(full_path) > os.path.getmtime(dest):
            tmp_dest = dest + ".tmp"
            shutil.copy2(full_path, tmp_dest)
            os.replace(tmp_dest, dest)
        filename = safe_name
        subfolder = "loadlast_img_previews"
        view_type = "temp"

    if subfolder == ".":
        subfolder = ""

    return {
        "filename": filename,
        "subfolder": subfolder,
        "type": view_type,
    }


# ─── Node Class ─────────────────────────────────────────────────────────

class LoadLastImage:
    """
    Automatically load the most recently generated image(s).

    Scans ComfyUI's output and temp directories for the newest image files,
    loads them as an IMAGE tensor batch, and outputs rich metadata. Shows
    an inline preview that loads *immediately* when the node is placed
    (no queue needed).
    """

    CATEGORY = "FFMPEGA"
    FUNCTION = "load"
    OUTPUT_NODE = True

    RETURN_TYPES = ("IMAGE", "MASK", "STRING", "INT", "INT", "INT")
    RETURN_NAMES = ("images", "mask", "image_path", "width", "height", "image_count")

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "refresh_mode": (["auto", "manual"], {
                    "default": "auto",
                    "tooltip": "auto: reload when latest image changes. manual: only on input change.",
                }),
                "batch_size": ("INT", {
                    "default": 1,
                    "min": 1,
                    "max": 64,
                    "step": 1,
                    "tooltip": "Number of recent images to load as a batch.",
                }),
                "pin_index": ("INT", {
                    "default": 0,
                    "min": 0,
                    "max": BIGMAX,
                    "step": 1,
                    "tooltip": "Pin a specific iteration. 0 = disabled (auto-load latest).",
                }),
            },
            "optional": {
                "source_folder": ("STRING", {
                    "default": "",
                    "tooltip": "Custom folder to scan. Empty = default output/temp directories.",
                }),
                "filename_filter": ("STRING", {
                    "default": "",
                    "tooltip": "Only load files starting with this prefix.",
                }),
                "mask": ("MASK", {
                    "tooltip": (
                        "Optional upstream MASK pass-through. When "
                        "connected, this mask is forwarded instead of "
                        "the auto-generated one."
                    ),
                }),
            },
            "hidden": {
                "unique_id": "UNIQUE_ID",
                "_edit_state": ("STRING", {"default": "{}"}),
            },
        }

    @classmethod
    def IS_CHANGED(cls, refresh_mode="auto", **kwargs):
        """Content-aware change detection.

        In auto mode, returns a hash based on the latest image's filename
        and mtime so the node only re-runs when a new image appears.
        In manual mode, returns a constant so it never auto-reruns —
        unless the user has explicitly selected an image or applied edits.
        """
        uid = str(kwargs.get("unique_id", ""))

        # Evict stale entries (TTL-based)
        global _last_eviction_scan_time
        now = time.time()
        if now - _last_eviction_scan_time > _EVICTION_SCAN_INTERVAL:
            _last_eviction_scan_time = now
            for d in (_user_image_selections, _user_edit_states):
                stale = [k for k, v in d.items() if now - v.get("ts", 0) > _SERVER_STATE_TTL]
                for k in stale:
                    d.pop(k, None)

        # Force re-run if user selected an image or applied edits
        if uid and uid in _user_image_selections:
            return f"selected_{uid}_{time.time()}"
        if uid and uid in _user_edit_states:
            return f"edits_{uid}_{time.time()}"

        if refresh_mode == "manual":
            return ""

        # Find the latest image and hash its identity
        source = kwargs.get("source_folder", "")
        prefix = kwargs.get("filename_filter", "")

        scan_dirs = _resolve_scan_dirs(source)
        info = _find_latest_image_info(scan_dirs, prefix)
        if info is None:
            return ""

        m = hashlib.sha256()
        m.update(info["filename"].encode())
        m.update(str(info.get("mtime", 0)).encode())
        m.update(str(kwargs.get("batch_size", 1)).encode())
        m.update(str(kwargs.get("_edit_state", "{}")).encode())
        return m.hexdigest()

    def load(
        self,
        refresh_mode: str = "auto",
        batch_size: int = 1,
        pin_index: int = 0,
        source_folder: str = "",
        filename_filter: str = "",
        mask=None,
        unique_id: str = "",
        _edit_state: str = "{}",
    ):
        """Main execution function."""
        scanner = FilesystemScanner()
        cache = ImageExecutionCache.get_instance()

        empty_image = torch.zeros(1, 512, 512, 3)
        empty_mask = torch.ones(1, 512, 512)
        empty_result = (empty_image, empty_mask, "", 512, 512, 0)

        # --- Handle pinned image ---
        if pin_index > 0:
            pinned = cache.get_pinned(pin_index)
            if pinned is not None:
                tensor = pinned.tensor
                if tensor.ndim == 3:
                    tensor = tensor.unsqueeze(0)
                h, w = tensor.shape[1], tensor.shape[2]
                mask = torch.ones(tensor.shape[0], h, w, dtype=torch.float32)
                return {
                    "ui": {"images": []},
                    "result": (tensor, mask, "", w, h, tensor.shape[0]),
                }
            else:
                logger.warning(
                    "[LoadLastImage] Pinned iteration %d not in cache, falling back",
                    pin_index,
                )

        # --- Resolve image source ---
        resolved_path = None
        info = None

        # Check for user-selected image from browser strip
        if unique_id:
            sel_wrapper = _user_image_selections.pop(str(unique_id), None)
            sel = sel_wrapper.get("data") if isinstance(sel_wrapper, dict) else None
            if sel:
                sel_filename = os.path.basename(sel.get("filename", ""))
                sel_subfolder = sel.get("subfolder", "")
                sel_type = sel.get("type", "output")
                # Reject path-traversal
                if ".." in sel_subfolder.replace("\\", "/").split("/"):
                    logger.warning(
                        "[LoadLastImage] Subfolder contains '..', rejecting for node %s",
                        unique_id,
                    )
                    sel_filename = ""
                if sel_type not in _ALLOWED_SEL_TYPES:
                    sel_filename = ""
                if sel_filename:
                    if sel_type == "output":
                        base = folder_paths.get_output_directory()
                    else:
                        base = folder_paths.get_temp_directory()
                    candidate = (
                        os.path.join(base, sel_subfolder, sel_filename)
                        if sel_subfolder
                        else os.path.join(base, sel_filename)
                    )
                    if _is_path_sandboxed(candidate) and os.path.isfile(candidate):
                        resolved_path = candidate
                        info = {
                            "filename": sel_filename,
                            "subfolder": sel_subfolder,
                            "type": sel_type,
                        }
                        logger.info(
                            "[LoadLastImage] Using user-selected image: %s",
                            resolved_path,
                        )

        if resolved_path is None:
            # Auto-discover latest images
            scan_dirs = _resolve_scan_dirs(source_folder)
            paths = scanner.scan(
                scan_dirs,
                n=batch_size,
                filename_filter=filename_filter,
            )
            if not paths:
                logger.warning("[LoadLastImage] No images found")
                return {"ui": {"images": []}, "result": empty_result}

            resolved_path = paths[0]
            parent = os.path.dirname(resolved_path)
            info = _resolve_view_info(resolved_path, parent)

            # Load batch
            images: list[torch.Tensor] = []
            for path in paths:
                try:
                    tensor, _meta = scanner.load_image(path)
                    images.append(tensor)
                except Exception:
                    logger.warning("[LoadLastImage] Skipping corrupted: %s", path)
                    continue

            if not images:
                logger.warning("[LoadLastImage] All images corrupted")
                return {"ui": {"images": []}, "result": empty_result}

            # Ensure all images match first image's dimensions
            target_h, target_w = images[0].shape[0], images[0].shape[1]
            resized = []
            for img in images:
                if img.shape[0] != target_h or img.shape[1] != target_w:
                    img_nchw = img.permute(2, 0, 1).unsqueeze(0)
                    img_nchw = F.interpolate(
                        img_nchw, size=(target_h, target_w),
                        mode='bilinear', align_corners=False,
                    )
                    img = img_nchw.squeeze(0).permute(1, 2, 0)
                resized.append(img)

            batch_tensor = torch.stack(resized, dim=0)
            batch_count = len(resized)
            mask = torch.ones(batch_count, target_h, target_w, dtype=torch.float32)

            # --- Apply edits if present ---
            # Server-side edits take precedence
            if unique_id and str(unique_id) in _user_edit_states:
                edits_wrapper = _user_edit_states.pop(str(unique_id))
                edits = edits_wrapper.get("data", {}) if isinstance(edits_wrapper, dict) else {}
                if edits:
                    batch_tensor, mask = self._apply_edits(batch_tensor, mask, edits)
                    target_h, target_w = batch_tensor.shape[1], batch_tensor.shape[2]
            elif _edit_state and _edit_state != "{}":
                try:
                    edits = json.loads(_edit_state)
                    if edits:
                        batch_tensor, mask = self._apply_edits(batch_tensor, mask, edits)
                        target_h, target_w = batch_tensor.shape[1], batch_tensor.shape[2]
                except (json.JSONDecodeError, TypeError):
                    pass

            logger.info(
                "[LoadLastImage] Loaded %d image(s) | %dx%d | %s",
                batch_count, target_w, target_h, resolved_path,
            )

            # Build preview metadata
            preview = []
            if info:
                preview = [info]

            return {
                "ui": {"images": preview},
                "result": (
                    batch_tensor,
                    mask,
                    resolved_path,
                    target_w,
                    target_h,
                    batch_count,
                ),
            }

        # --- Single selected image path ---
        try:
            tensor, _meta = scanner.load_image(resolved_path)
        except Exception as e:
            logger.warning("[LoadLastImage] Failed to load: %s — %s", resolved_path, e)
            return {"ui": {"images": []}, "result": empty_result}

        if tensor.ndim == 3:
            tensor = tensor.unsqueeze(0)
        h, w = tensor.shape[1], tensor.shape[2]
        mask = torch.ones(tensor.shape[0], h, w, dtype=torch.float32)

        # Apply edits
        if unique_id and str(unique_id) in _user_edit_states:
            edits_wrapper = _user_edit_states.pop(str(unique_id))
            edits = edits_wrapper.get("data", {}) if isinstance(edits_wrapper, dict) else {}
            if edits:
                tensor, mask = self._apply_edits(tensor, mask, edits)
                h, w = tensor.shape[1], tensor.shape[2]
        elif _edit_state and _edit_state != "{}":
            try:
                edits = json.loads(_edit_state)
                if edits:
                    tensor, mask = self._apply_edits(tensor, mask, edits)
                    h, w = tensor.shape[1], tensor.shape[2]
            except (json.JSONDecodeError, TypeError):
                pass

        return {
            "ui": {"images": []},  # Custom DOM preview — suppress default output preview
            "result": (tensor, mask, resolved_path, w, h, tensor.shape[0]),
        }

    def _apply_edits(
        self,
        images: torch.Tensor,
        mask: torch.Tensor,
        edits: dict,
    ) -> tuple[torch.Tensor, torch.Tensor]:
        """Apply image edits (crop, resize, rotation, etc.) via PIL.

        Processes each image in the batch and returns updated tensors.
        Edit operations are applied in a fixed order:
        rotation → flip → crop → resize → padding → color → captions → overlays
        """
        from PIL import Image, ImageEnhance

        if not edits:
            return images, mask

        results = []
        for i in range(images.shape[0]):
            arr = (images[i].cpu().numpy() * 255).astype(np.uint8)
            img = Image.fromarray(arr)

            # Rotation
            rotation = edits.get("rotation")
            if rotation:
                try:
                    angle = int(rotation)
                    if angle in (90, 180, 270):
                        img = img.rotate(-angle, expand=True)
                except (ValueError, TypeError):
                    pass

            # Flip
            flip = edits.get("flip")
            if flip:
                if flip == "horizontal":
                    img = img.transpose(Image.FLIP_LEFT_RIGHT)
                elif flip == "vertical":
                    img = img.transpose(Image.FLIP_TOP_BOTTOM)

            # Crop
            crop_rect = edits.get("crop_rect")
            if crop_rect:
                try:
                    if isinstance(crop_rect, str):
                        crop_rect = json.loads(crop_rect)
                    x, y, w, h = (
                        int(crop_rect["x"]), int(crop_rect["y"]),
                        int(crop_rect["w"]), int(crop_rect["h"]),
                    )
                    if w > 0 and h > 0:
                        img = img.crop((x, y, x + w, y + h))
                except (KeyError, ValueError, TypeError, json.JSONDecodeError):
                    pass

            # Resize
            resize = edits.get("resize")
            if resize:
                try:
                    if isinstance(resize, str):
                        resize = json.loads(resize)
                    rw, rh = int(resize["w"]), int(resize["h"])
                    if rw > 0 and rh > 0:
                        img = img.resize((rw, rh), Image.LANCZOS)
                except (KeyError, ValueError, TypeError, json.JSONDecodeError):
                    pass

            # Padding
            padding = edits.get("padding")
            if padding:
                try:
                    if isinstance(padding, str):
                        padding = json.loads(padding)
                    pt = int(padding.get("top", 0))
                    pr = int(padding.get("right", 0))
                    pb = int(padding.get("bottom", 0))
                    pl = int(padding.get("left", 0))
                    color = padding.get("color", "#000000")
                    if any(v > 0 for v in (pt, pr, pb, pl)):
                        new_w = img.width + pl + pr
                        new_h = img.height + pt + pb
                        padded = Image.new("RGB", (new_w, new_h), color)
                        padded.paste(img, (pl, pt))
                        img = padded
                except (ValueError, TypeError, json.JSONDecodeError):
                    pass

            # Color adjustments
            brightness = edits.get("brightness")
            if brightness is not None:
                try:
                    val = float(brightness)
                    if val != 1.0:
                        img = ImageEnhance.Brightness(img).enhance(val)
                except (ValueError, TypeError):
                    pass

            contrast = edits.get("contrast")
            if contrast is not None:
                try:
                    val = float(contrast)
                    if val != 1.0:
                        img = ImageEnhance.Contrast(img).enhance(val)
                except (ValueError, TypeError):
                    pass

            saturation = edits.get("saturation")
            if saturation is not None:
                try:
                    val = float(saturation)
                    if val != 1.0:
                        img = ImageEnhance.Color(img).enhance(val)
                except (ValueError, TypeError):
                    pass

            # Convert back to tensor
            arr = np.array(img).astype(np.float32) / 255.0
            results.append(torch.from_numpy(arr))

        # Stack results, ensuring consistent dimensions
        if results:
            target_h, target_w = results[0].shape[0], results[0].shape[1]
            aligned = []
            for r in results:
                if r.shape[0] != target_h or r.shape[1] != target_w:
                    r_nchw = r.permute(2, 0, 1).unsqueeze(0)
                    r_nchw = F.interpolate(
                        r_nchw, size=(target_h, target_w),
                        mode='bilinear', align_corners=False,
                    )
                    r = r_nchw.squeeze(0).permute(1, 2, 0)
                aligned.append(r)
            images = torch.stack(aligned, dim=0)
            mask = torch.ones(
                images.shape[0], target_h, target_w, dtype=torch.float32,
            )

        return images, mask
