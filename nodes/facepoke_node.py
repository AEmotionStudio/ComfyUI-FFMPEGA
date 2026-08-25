"""FacePoke Node — Per-frame face puppeteering for LivePortrait.

Provides an inline editing UI where users can:
1. Browse video frames via a filmstrip scrubber
2. Click/drag faces for real-time pose editing
3. Adjust expression sliders per face
4. Apply edits to rebuild the video with modified frames only

Architecture follows the VideoEditor / LoadLastVideo patterns:
- Upstream inputs (images/video_path) always win over uploaded video
- Pause mode: pause via ExecutionBlocker, show editor, resume on Apply
- Passthrough mode: skip editing, pass video unchanged
- Upload button: upload video directly to the node

Note: The "FacePoke" name is inspired by https://github.com/jbilcke-hf/FacePoke
but this is a fully independent, ground-up implementation. There is no code
dependency, import, or shared logic with the upstream project. All face editing
logic uses our own LivePortrait synthesizer backend and custom expression
coefficient math.
"""

from __future__ import annotations

import atexit
import hashlib
import json
import logging
import os
import subprocess
import tempfile
import time
from collections import OrderedDict
from typing import Optional

import cv2
import numpy as np
import torch

logger = logging.getLogger("ffmpega")

# Lazy import to avoid circular deps at module load
_folder_paths = None


def _get_folder_paths():
    """Lazy-load ComfyUI's folder_paths module."""
    global _folder_paths
    if _folder_paths is None:
        try:
            import folder_paths
            _folder_paths = folder_paths
        except ImportError:
            pass
    return _folder_paths


# ── Server-side state (node_id → edit dict) ─────────────────────────────
_MAX_STATE_ENTRIES = 50

_facepoke_edit_states: OrderedDict[str, dict] = OrderedDict()
_facepoke_frame_cache: OrderedDict[str, dict] = OrderedDict()


def _capped_insert(store: OrderedDict, key: str, value: dict) -> None:
    """Insert into an ordered dict, evicting oldest if over cap."""
    if key in store:
        store.move_to_end(key)
    store[key] = value
    while len(store) > _MAX_STATE_ENTRIES:
        store.popitem(last=False)


def _resolve_video_path(video_path: str) -> str | None:
    """Resolve a video path to an absolute path.

    Handles relative paths like ``input/file.mp4`` by resolving them
    against ComfyUI's input directory via ``folder_paths``.
    """
    if not video_path:
        return None
    # Already absolute and exists?
    if os.path.isabs(video_path) and os.path.isfile(video_path):
        return video_path
    # Try CWD-relative
    if os.path.isfile(video_path):
        return os.path.abspath(video_path)
    # Resolve via folder_paths (handles "input/file.mp4")
    fp = _get_folder_paths()
    if fp:
        # Strip leading "input/" prefix if present
        clean = video_path
        for prefix in ("input/", "input\\"):
            if clean.startswith(prefix):
                clean = clean[len(prefix):]
                break
        try:
            input_dir = fp.get_input_directory()
            candidate = os.path.join(input_dir, clean)
            if os.path.isfile(candidate):
                return candidate
        except Exception:
            pass
        # Also try temp directory
        try:
            temp_dir = fp.get_temp_directory()
            candidate = os.path.join(temp_dir, clean)
            if os.path.isfile(candidate):
                return candidate
        except Exception:
            pass
        # Try output directory
        try:
            out_dir = fp.get_output_directory()
            candidate = os.path.join(out_dir, clean)
            if os.path.isfile(candidate):
                return candidate
        except Exception:
            pass
    return None


# ── API Routes ──────────────────────────────────────────────────────────

try:
    from aiohttp import web
    from server import PromptServer  # type: ignore[import-not-found]

    @PromptServer.instance.routes.post("/facepoke/apply_edits")
    async def _api_apply_edits(request):
        """Store per-frame/per-face edit state, then trigger re-queue."""
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "invalid JSON"}, status=400)

        node_id = str(body.get("node_id", ""))
        if not node_id:
            return web.json_response({"error": "node_id required"}, status=400)

        edits = body.get("edits")  # dict of frame_idx → face edits
        if edits:
            _capped_insert(_facepoke_edit_states, node_id, {
                "data": edits, "ts": time.time(),
            })
            logger.info("[FacePoke] Edit state stored for node %s "
                        "(%d frames)", node_id, len(edits))
        else:
            _facepoke_edit_states.pop(node_id, None)
            logger.debug("[FacePoke] Edit state cleared for node %s",
                         node_id)

        return web.json_response({"ok": True})

    @PromptServer.instance.routes.post("/facepoke/get_frames")
    async def _api_get_frames(request):
        """Return frame metadata for a video (used by filmstrip)."""
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "invalid JSON"}, status=400)

        node_id = str(body.get("node_id", ""))
        raw_path = str(body.get("video_path", ""))
        video_path = _resolve_video_path(raw_path)

        if not video_path:
            return web.json_response(
                {"error": f"video_path not found: {raw_path}"}, status=400)

        cache = _facepoke_frame_cache.get(node_id, {})
        if cache.get("path") == video_path and cache.get("meta"):
            return web.json_response(cache["meta"])

        # Extract basic metadata
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return web.json_response(
                {"error": "could not open video"}, status=400)

        fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        cap.release()

        meta = {
            "fps": fps,
            "total_frames": total_frames,
            "width": width,
            "height": height,
        }

        _capped_insert(_facepoke_frame_cache, node_id, {
            "path": video_path, "meta": meta,
        })

        return web.json_response(meta)

    @PromptServer.instance.routes.post("/facepoke/get_frame")
    async def _api_get_frame(request):
        """Return a single frame as JPEG for the editor canvas."""
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "invalid JSON"}, status=400)

        raw_path = str(body.get("video_path", ""))
        frame_idx = int(body.get("frame_idx", 0))
        video_path = _resolve_video_path(raw_path)

        if not video_path:
            return web.json_response(
                {"error": f"video_path not found: {raw_path}"}, status=400)

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return web.json_response(
                {"error": "could not open video"}, status=400)

        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = cap.read()
        cap.release()

        if not ret or frame is None:
            return web.json_response(
                {"error": f"frame {frame_idx} not readable"}, status=400)

        _, jpg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
        return web.Response(
            body=jpg.tobytes(),
            content_type="image/jpeg",
        )

    @PromptServer.instance.routes.post("/facepoke/detect_faces")
    async def _api_detect_faces(request):
        """Detect faces in a specific frame and return bounding boxes."""
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "invalid JSON"}, status=400)

        raw_path = str(body.get("video_path", ""))
        frame_idx = int(body.get("frame_idx", 0))
        use_blaze = bool(body.get("use_blaze", False))
        video_path = _resolve_video_path(raw_path)

        if not video_path:
            return web.json_response(
                {"error": f"video_path not found: {raw_path}"}, status=400)

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return web.json_response(
                {"error": "could not open video"}, status=400)

        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = cap.read()
        cap.release()

        if not ret or frame is None:
            return web.json_response(
                {"error": f"frame {frame_idx} not readable"}, status=400)

        # Detect faces
        try:
            try:
                from ..core.liveportrait_synthesizer import (
                    _detect_all_faces,
                )
            except ImportError:
                from core.liveportrait_synthesizer import (  # type: ignore
                    _detect_all_faces,
                )
            bboxes = _detect_all_faces(frame, use_blaze_fallback=use_blaze)
        except Exception as e:
            logger.warning("[FacePoke] Face detection failed: %s", e)
            bboxes = []

        faces = []
        for i, bbox in enumerate(bboxes):
            x1, y1, x2, y2 = int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3])
            faces.append({
                "idx": i,
                "bbox": [x1, y1, x2, y2],
                "center": [(x1 + x2) // 2, (y1 + y2) // 2],
            })

        return web.json_response({
            "faces": faces,
            "frame_idx": frame_idx,
            "width": frame.shape[1],
            "height": frame.shape[0],
        })

    @PromptServer.instance.routes.post("/facepoke/get_frame_with_landmarks")
    async def _api_get_frame_with_landmarks(request):
        """Return a frame JPEG with face landmarks drawn on it.

        Draws MediaPipe face mesh contours (jaw, lips, eyes, eyebrows,
        nose) on the frame in distinct colors per face.
        """
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "invalid JSON"}, status=400)

        raw_path = str(body.get("video_path", ""))
        frame_idx = int(body.get("frame_idx", 0))
        selected_face = int(body.get("selected_face", -1))
        video_path = _resolve_video_path(raw_path)

        if not video_path:
            return web.json_response(
                {"error": f"video_path not found: {raw_path}"}, status=400)

        cap = cv2.VideoCapture(video_path)
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = cap.read()
        cap.release()

        if not ret or frame is None:
            return web.json_response(
                {"error": f"frame {frame_idx} not readable"}, status=400)

        # Draw landmarks using MediaPipe
        try:
            import mediapipe as mp
            try:
                from ..core.musetalk.face_detection import _get_landmarker
            except ImportError:
                from core.musetalk.face_detection import _get_landmarker  # type: ignore

            h, w = frame.shape[:2]
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            landmarker = _get_landmarker()
            result = landmarker.detect(mp_image)

            # Colors for different faces (BGR)
            face_colors = [
                (241, 102, 99),   # indigo-ish
                (94, 197, 34),    # green
                (68, 68, 239),    # red-ish
                (180, 130, 70),   # teal
                (60, 180, 220),   # orange
            ]

            if result.face_landmarks:
                # Hardcoded face mesh connection groups
                # (replaces deprecated mp.solutions.face_mesh constants)
                _FACE_OVAL = frozenset([
                    (10, 338), (338, 297), (297, 332), (332, 284),
                    (284, 251), (251, 389), (389, 356), (356, 454),
                    (454, 323), (323, 361), (361, 288), (288, 397),
                    (397, 365), (365, 379), (379, 378), (378, 400),
                    (400, 377), (377, 152), (152, 148), (148, 176),
                    (176, 149), (149, 150), (150, 136), (136, 172),
                    (172, 58), (58, 132), (132, 93), (93, 234),
                    (234, 127), (127, 162), (162, 21), (21, 54),
                    (54, 103), (103, 67), (67, 109), (109, 10),
                ])
                _LIPS = frozenset([
                    (61, 146), (146, 91), (91, 181), (181, 84),
                    (84, 17), (17, 314), (314, 405), (405, 321),
                    (321, 375), (375, 291), (291, 409), (409, 270),
                    (270, 269), (269, 267), (267, 0), (0, 37),
                    (37, 39), (39, 40), (40, 185), (185, 61),
                    (78, 95), (95, 88), (88, 178), (178, 87),
                    (87, 14), (14, 317), (317, 402), (402, 318),
                    (318, 324), (324, 308), (308, 415), (415, 310),
                    (310, 311), (311, 312), (312, 13), (13, 82),
                    (82, 81), (81, 80), (80, 191), (191, 78),
                ])
                _LEFT_EYE = frozenset([
                    (263, 249), (249, 390), (390, 373), (373, 374),
                    (374, 380), (380, 381), (381, 382), (382, 362),
                    (362, 398), (398, 384), (384, 385), (385, 386),
                    (386, 387), (387, 388), (388, 466), (466, 263),
                ])
                _RIGHT_EYE = frozenset([
                    (33, 7), (7, 163), (163, 144), (144, 145),
                    (145, 153), (153, 154), (154, 155), (155, 133),
                    (133, 173), (173, 157), (157, 158), (158, 159),
                    (159, 160), (160, 161), (161, 246), (246, 33),
                ])
                _LEFT_EYEBROW = frozenset([
                    (276, 283), (283, 282), (282, 295), (295, 285),
                    (300, 293), (293, 334), (334, 296), (296, 336),
                ])
                _RIGHT_EYEBROW = frozenset([
                    (46, 53), (53, 52), (52, 65), (65, 55),
                    (70, 63), (63, 105), (105, 66), (66, 107),
                ])
                connections_map = {
                    "jaw": _FACE_OVAL,
                    "lips": _LIPS,
                    "left_eye": _LEFT_EYE,
                    "right_eye": _RIGHT_EYE,
                    "left_eyebrow": _LEFT_EYEBROW,
                    "right_eyebrow": _RIGHT_EYEBROW,
                }

                for fi, face_landmarks in enumerate(result.face_landmarks):
                    color = face_colors[fi % len(face_colors)]
                    is_selected = (fi == selected_face or selected_face < 0)
                    alpha = 1.0 if is_selected else 0.3
                    thickness = 2 if is_selected else 1

                    # Convert landmarks to pixel coords
                    pts = []
                    for lm in face_landmarks:
                        px = int(lm.x * w)
                        py = int(lm.y * h)
                        pts.append((px, py))

                    # Draw connections for each group
                    for _group_name, conns in connections_map.items():
                        for conn in conns:
                            p1 = pts[conn[0]]
                            p2 = pts[conn[1]]
                            draw_color = tuple(
                                int(c * alpha) for c in color)
                            cv2.line(frame, p1, p2, draw_color, thickness,
                                     cv2.LINE_AA)

                    # Draw key landmarks as dots (eyes, nose tip, lips)
                    key_indices = [
                        1,    # nose tip
                        33,   # right eye inner
                        133,  # right eye outer
                        362,  # left eye inner
                        263,  # left eye outer
                        61,   # right mouth corner
                        291,  # left mouth corner
                        0,    # upper lip center
                        17,   # lower lip center
                    ]
                    for ki in key_indices:
                        if ki < len(pts):
                            cv2.circle(frame, pts[ki], 3, color,
                                       -1, cv2.LINE_AA)

        except Exception as e:
            logger.error("[FacePoke] Landmark drawing failed: %s", e,
                         exc_info=True)
            # Fall through — return frame without landmarks

        _, jpg = cv2.imencode(
            ".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        return web.Response(
            body=jpg.tobytes(), content_type="image/jpeg")

    @PromptServer.instance.routes.post("/facepoke/preview")
    async def _api_preview(request):
        """Apply expression edits to a single frame and return JPEG.

        This is the "live preview" endpoint — called repeatedly as user
        drags faces or adjusts sliders.
        """
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "invalid JSON"}, status=400)

        raw_path = str(body.get("video_path", ""))
        frame_idx = int(body.get("frame_idx", 0))
        face_edits = body.get("face_edits", {})
        use_blaze = bool(body.get("use_blaze", False))
        cached_bboxes_raw = body.get("cached_bboxes", None)
        # face_edits: { "0": { "rotate_pitch": 5.0, "smile": 0.8, ... }, ... }
        video_path = _resolve_video_path(raw_path)

        if not video_path:
            return web.json_response(
                {"error": f"video_path not found: {raw_path}"}, status=400)

        # Read the frame
        cap = cv2.VideoCapture(video_path)
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = cap.read()
        cap.release()

        if not ret or frame is None:
            return web.json_response(
                {"error": f"frame {frame_idx} not readable"}, status=400)

        # If no edits, just return the original frame
        if not face_edits:
            _, jpg = cv2.imencode(
                ".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
            return web.Response(
                body=jpg.tobytes(), content_type="image/jpeg")

        # Convert cached bboxes from JSON to tuples if provided
        cached_bboxes = None
        if cached_bboxes_raw and isinstance(cached_bboxes_raw, list):
            cached_bboxes = [tuple(b) for b in cached_bboxes_raw]

        # Apply LivePortrait edits to each face
        try:
            result_frame = _apply_face_edits(frame, face_edits,
                                              use_blaze=use_blaze,
                                              cached_bboxes=cached_bboxes)
        except Exception as e:
            logger.error("[FacePoke] Preview failed: %s", e, exc_info=True)
            return web.json_response(
                {"error": f"Preview failed: {e}"},
                status=500,
            )

        _, jpg = cv2.imencode(
            ".jpg", result_frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        return web.Response(
            body=jpg.tobytes(), content_type="image/jpeg")

    # ── Server-side driving keypoint cache ────────────────────────────
    _driving_cache: dict = {}

    @PromptServer.instance.routes.post("/facepoke/extract_driving")
    async def _api_extract_driving(request):
        """Extract motion keypoints from every frame of a driving video.

        Returns a driving_id that can be used in subsequent preview calls.
        Keypoints are cached server-side.
        """
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "invalid JSON"}, status=400)

        raw_path = str(body.get("video_path", ""))
        crop_factor = float(body.get("crop_factor", 1.6))

        # Support both absolute paths and ComfyUI input paths
        video_path = _resolve_video_path(raw_path)
        if not video_path:
            return web.json_response(
                {"error": f"video_path not found: {raw_path}"}, status=400)

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return web.json_response(
                {"error": "could not open driving video"}, status=400)

        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0

        try:
            try:
                from ..core.liveportrait_synthesizer import (
                    load_models, _detect_face_bbox, _crop_face,
                    _prepare_source, _get_kp_info, _transform_keypoint,
                )
            except ImportError:
                from core.liveportrait_synthesizer import (  # type: ignore
                    load_models, _detect_face_bbox, _crop_face,
                    _prepare_source, _get_kp_info, _transform_keypoint,
                )

            models = load_models()
            me = models["motion_extractor"]
            device = models["device"]
            me.to(device)

            keypoints = []
            frame_idx = 0
            while True:
                ret, frame = cap.read()
                if not ret:
                    break

                bbox = _detect_face_bbox(frame)
                if bbox is None:
                    # No face — store None placeholder
                    keypoints.append(None)
                    frame_idx += 1
                    continue

                crop_256, _, _ = _crop_face(frame, bbox, expand=crop_factor)
                rgb = cv2.cvtColor(crop_256, cv2.COLOR_BGR2RGB)
                tensor = _prepare_source(rgb, device)

                with torch.no_grad():
                    kp_info = _get_kp_info(me, tensor)
                    kp = _transform_keypoint(kp_info)

                # Store as CPU list for serialization
                keypoints.append(kp.cpu().tolist())
                frame_idx += 1

            # Offload
            offload = models["offload_device"]
            try:
                me.to(offload)
            except Exception:
                pass

        finally:
            cap.release()

        if not keypoints:
            return web.json_response(
                {"error": "No frames extracted from driving video"},
                status=400)

        import hashlib
        driving_id = hashlib.md5(
            f"{video_path}:{total}".encode()).hexdigest()[:12]
        _driving_cache[driving_id] = {
            "keypoints": keypoints,
            "total": len(keypoints),
            "fps": fps,
            "path": video_path,
        }

        logger.info("[FacePoke] Extracted %d keypoints from driving video "
                     "(id=%s)", len(keypoints), driving_id)

        return web.json_response({
            "driving_id": driving_id,
            "total_frames": len(keypoints),
            "fps": fps,
            "faces_found": sum(1 for k in keypoints if k is not None),
        })

    @PromptServer.instance.routes.post("/facepoke/extract_ref_expression")
    async def _api_extract_ref_expression(request):
        """Extract expression keypoints from a reference image.

        Accepts base64-encoded image data and returns serialized keypoints.
        """
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "invalid JSON"}, status=400)

        image_data = body.get("image_data", "")
        crop_factor = float(body.get("crop_factor", 1.6))

        if not image_data:
            return web.json_response(
                {"error": "image_data is required"}, status=400)

        # Decode base64 image
        import base64
        try:
            img_bytes = base64.b64decode(image_data.split(",")[-1])
            nparr = np.frombuffer(img_bytes, np.uint8)
            image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        except Exception as e:
            return web.json_response(
                {"error": f"Failed to decode image: {e}"}, status=400)

        if image is None:
            return web.json_response(
                {"error": "Failed to decode image"}, status=400)

        try:
            try:
                from ..core.liveportrait_synthesizer import (
                    load_models, _detect_face_bbox, _crop_face,
                    _prepare_source, _get_kp_info, _transform_keypoint,
                )
            except ImportError:
                from core.liveportrait_synthesizer import (  # type: ignore
                    load_models, _detect_face_bbox, _crop_face,
                    _prepare_source, _get_kp_info, _transform_keypoint,
                )

            bbox = _detect_face_bbox(image)
            if bbox is None:
                return web.json_response(
                    {"error": "No face detected in reference image"},
                    status=400)

            models = load_models()
            me = models["motion_extractor"]
            device = models["device"]
            me.to(device)

            try:
                crop_256, _, _ = _crop_face(image, bbox, expand=crop_factor)
                rgb = cv2.cvtColor(crop_256, cv2.COLOR_BGR2RGB)
                tensor = _prepare_source(rgb, device)
                with torch.no_grad():
                    kp_info = _get_kp_info(me, tensor)
                    kp = _transform_keypoint(kp_info)
                kp_list = kp.cpu().tolist()
            finally:
                offload = models["offload_device"]
                try:
                    me.to(offload)
                except Exception:
                    pass

        except Exception as e:
            logger.error("[FacePoke] Ref expression extraction failed: %s",
                         e, exc_info=True)
            return web.json_response(
                {"error": f"Expression extraction failed: {e}"}, status=500)

        return web.json_response({
            "ref_kp": kp_list,
            "bbox": [int(x) for x in bbox],
        })

    @PromptServer.instance.routes.post("/facepoke/apply_ref_preview")
    async def _api_apply_ref_preview(request):
        """Generate a preview with reference expression applied.

        Supports both driving video keypoints and reference image expression.
        """
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "invalid JSON"}, status=400)

        raw_path = str(body.get("video_path", ""))
        frame_idx = int(body.get("frame_idx", 0))
        ref_kp = body.get("ref_kp", None)
        driving_id = body.get("driving_id", None)
        driving_frame = body.get("driving_frame", None)
        multiplier = float(body.get("multiplier", 1.0))
        ratio = float(body.get("ratio", 1.0))
        parts = str(body.get("parts", "all"))
        face_idx = int(body.get("face_idx", 0))
        use_blaze = bool(body.get("use_blaze", False))
        cached_bboxes_raw = body.get("cached_bboxes", None)
        # Also apply slider edits on top
        slider_edits = body.get("slider_edits", None)

        video_path = _resolve_video_path(raw_path)
        if not video_path:
            return web.json_response(
                {"error": f"video_path not found: {raw_path}"}, status=400)

        cap = cv2.VideoCapture(video_path)
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = cap.read()
        cap.release()
        if not ret or frame is None:
            return web.json_response(
                {"error": f"frame {frame_idx} not readable"}, status=400)

        try:
            try:
                from ..core.liveportrait_synthesizer import (
                    load_models, _detect_all_faces, _crop_face,
                    _prepare_source, _get_kp_info, _transform_keypoint,
                    _do_stitching, _warp_decode, _paste_back,
                    transfer_expression,
                )
            except ImportError:
                from core.liveportrait_synthesizer import (  # type: ignore
                    load_models, _detect_all_faces, _crop_face,
                    _prepare_source, _get_kp_info, _transform_keypoint,
                    _do_stitching, _warp_decode, _paste_back,
                    transfer_expression,
                )

            # Convert cached bboxes if provided
            cached_bboxes = None
            if cached_bboxes_raw and isinstance(cached_bboxes_raw, list):
                cached_bboxes = [tuple(b) for b in cached_bboxes_raw]

            if cached_bboxes:
                bboxes = cached_bboxes
            else:
                bboxes = _detect_all_faces(frame, use_blaze_fallback=use_blaze)

            if face_idx >= len(bboxes):
                if not bboxes:
                    # Return unmodified frame
                    _, jpg = cv2.imencode(
                        ".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                    return web.Response(
                        body=jpg.tobytes(), content_type="image/jpeg")
                face_idx = 0

            models = load_models()
            afe = models["appearance_feature_extractor"]
            me = models["motion_extractor"]
            wn = models["warping_module"]
            sg = models["spade_generator"]
            srm = models["stitching_retargeting_module"]
            device = models["device"]

            for m in (afe, me, wn, sg):
                m.to(device)
            if isinstance(srm, dict):
                for v in srm.values():
                    if hasattr(v, "to"):
                        v.to(device)

            bbox = bboxes[face_idx]
            crop_256, M, M_inv = _crop_face(frame, bbox, expand=1.7)
            rgb = cv2.cvtColor(crop_256, cv2.COLOR_BGR2RGB)
            tensor = _prepare_source(rgb, device)

            with torch.no_grad():
                source_feature_3d = afe(tensor).float()
                source_kp_info = _get_kp_info(me, tensor)
                source_kp = _transform_keypoint(source_kp_info)

                # Start from source keypoints
                kp_driving = source_kp.clone()

                # Apply driving video motion (relative)
                if driving_id and driving_frame is not None:
                    drv_data = _driving_cache.get(driving_id)
                    if drv_data:
                        kps = drv_data["keypoints"]
                        drv_f = int(driving_frame)
                        if (0 <= drv_f < len(kps) and
                                kps[drv_f] is not None and kps[0] is not None):
                            drv_kp = torch.tensor(
                                kps[drv_f], device=device).float()
                            drv_kp_0 = torch.tensor(
                                kps[0], device=device).float()
                            delta = (drv_kp - drv_kp_0) * multiplier
                            kp_driving = source_kp + delta

                # Apply reference image expression
                if ref_kp is not None:
                    ref_tensor = torch.tensor(
                        ref_kp, device=device).float()
                    kp_driving = transfer_expression(
                        kp_driving, ref_tensor,
                        parts=parts, ratio=ratio)

                # Apply slider edits on top (if any)
                if slider_edits:
                    from ..core.liveportrait_synthesizer import (
                        calc_expression_delta, get_rotation_matrix,
                    )
                    e_delta = torch.zeros_like(
                        source_kp_info['exp'])
                    # Parse slider params same as _apply_face_edits
                    _sp = {}
                    for key in ("smile", "blink", "blink_left", "blink_right",
                                "eyebrow", "eyebrow_left", "eyebrow_right",
                                "wink", "pupil_x", "pupil_y",
                                "aaa", "eee", "woo",
                                "rotate_pitch", "rotate_yaw", "rotate_roll"):
                        try:
                            _sp[key] = float(slider_edits.get(key, 0.0))
                        except (TypeError, ValueError):
                            _sp[key] = 0.0
                    kp_driving, _ = calc_expression_delta(
                        kp_driving, **_sp)

                # Stitching
                stitching_net = (srm["stitching"]
                                if isinstance(srm, dict) else None)
                kp_driving = _do_stitching(
                    stitching_net, source_kp, kp_driving)

                # Warp + decode
                out_img = _warp_decode(
                    wn, sg, source_feature_3d, source_kp, kp_driving)

            result = _paste_back(frame.copy(), out_img, M_inv)

            # Offload
            offload = models["offload_device"]
            for m in (afe, me, wn, sg):
                try:
                    m.to(offload)
                except Exception:
                    pass
            if isinstance(srm, dict):
                for v in srm.values():
                    if hasattr(v, "to"):
                        try:
                            v.to(offload)
                        except Exception:
                            pass

        except Exception as e:
            logger.error("[FacePoke] Ref preview failed: %s",
                         e, exc_info=True)
            return web.json_response(
                {"error": f"Preview failed: {e}"}, status=500)

        _, jpg = cv2.imencode(
            ".jpg", result, [cv2.IMWRITE_JPEG_QUALITY, 85])
        return web.Response(
            body=jpg.tobytes(), content_type="image/jpeg")

except (ImportError, AttributeError):
    # Running outside ComfyUI (e.g. pytest) — skip route registration
    logger.debug("[FacePoke] API routes skipped (no PromptServer)")


# ── Helper: apply face edits to a single frame ─────────────────────────

@torch.no_grad()
def _apply_face_edits(
    frame: np.ndarray,
    face_edits: dict,
    crop_factor: float = 1.7,
    use_blaze: bool = False,
    cached_bboxes: list[tuple] | None = None,
) -> np.ndarray:
    """Apply expression edits to detected faces in a single frame.

    Args:
        frame: BGR frame (HxWx3).
        face_edits: Dict mapping face_idx (str) → param dict.
        crop_factor: Face crop expansion.
        use_blaze: If True, use blazeface fallback for detection.
        cached_bboxes: Pre-detected face bboxes to skip re-detection.

    Returns:
        Frame with edited face(s) composited back.
    """
    try:
        from ..core.liveportrait_synthesizer import (
            load_models, _detect_all_faces, _crop_face,
            _prepare_source, _get_kp_info, _transform_keypoint,
            calc_expression_delta, _do_stitching, _warp_decode,
            get_rotation_matrix, _paste_back,
        )
    except ImportError:
        from core.liveportrait_synthesizer import (  # type: ignore
            load_models, _detect_all_faces, _crop_face,
            _prepare_source, _get_kp_info, _transform_keypoint,
            calc_expression_delta, _do_stitching, _warp_decode,
            get_rotation_matrix, _paste_back,
        )

    # Use cached bboxes if provided, otherwise detect
    if cached_bboxes:
        bboxes = cached_bboxes
    else:
        bboxes = _detect_all_faces(frame, use_blaze_fallback=use_blaze)
    if not bboxes:
        return frame

    models = load_models()
    afe = models["appearance_feature_extractor"]
    me = models["motion_extractor"]
    wn = models["warping_module"]
    sg = models["spade_generator"]
    srm = models["stitching_retargeting_module"]
    device = models["device"]

    # Move to GPU
    for m in (afe, me, wn, sg):
        m.to(device)
    if isinstance(srm, dict):
        for v in srm.values():
            if hasattr(v, "to"):
                v.to(device)

    result = frame.copy()

    try:
        for face_idx_str, params in face_edits.items():
            face_idx = int(face_idx_str)
            if face_idx >= len(bboxes):
                continue

            bbox = bboxes[face_idx]
            crop_256, M, M_inv = _crop_face(frame, bbox, expand=crop_factor)
            rgb = cv2.cvtColor(crop_256, cv2.COLOR_BGR2RGB)
            tensor = _prepare_source(rgb, device)

            # Extract features
            source_feature_3d = afe(tensor).float()
            source_kp_info = _get_kp_info(me, tensor)
            source_kp = _transform_keypoint(source_kp_info)

            # Parse expression params from UI
            expr_params = {}
            for key in ("smile", "blink", "blink_left", "blink_right",
                        "eyebrow", "eyebrow_left", "eyebrow_right",
                        "wink", "pupil_x", "pupil_y",
                        "aaa", "eee", "woo",
                        "rotate_pitch", "rotate_yaw", "rotate_roll"):
                val = params.get(key, 0.0)
                try:
                    expr_params[key] = float(val)
                except (TypeError, ValueError):
                    expr_params[key] = 0.0

            # ── Build expression delta tensor
            e_delta = torch.zeros_like(source_kp_info['exp'])  # (1, 21, 3)

            # Rotation accumulators (degrees)
            r_pitch = expr_params.get("rotate_pitch", 0.0)
            r_yaw = -expr_params.get("rotate_yaw", 0.0)  # negate yaw like ALP
            r_roll = expr_params.get("rotate_roll", 0.0)

            smile = expr_params.get("smile", 0.0)
            mouth = expr_params.get("aaa", 0.0)
            eee_v = expr_params.get("eee", 0.0)
            woo_v = expr_params.get("woo", 0.0)
            wink = expr_params.get("wink", 0.0)
            pupil_x = expr_params.get("pupil_x", 0.0)
            pupil_y = expr_params.get("pupil_y", 0.0)

            # ── Eyes: support left/right split or combined "blink"
            blink_l = expr_params.get("blink_left", 0.0)
            blink_r = expr_params.get("blink_right", 0.0)
            blink_both = expr_params.get("blink", 0.0)
            if blink_both != 0 and blink_l == 0 and blink_r == 0:
                blink_l = blink_both
                blink_r = blink_both

            # ── Eyebrows: support left/right split or combined
            eb_l = expr_params.get("eyebrow_left", 0.0)
            eb_r = expr_params.get("eyebrow_right", 0.0)
            eb_both = expr_params.get("eyebrow", 0.0)
            if eb_both != 0 and eb_l == 0 and eb_r == 0:
                eb_l = eb_both
                eb_r = eb_both

            # Smile
            e_delta[0, 20, 1] += smile * -0.01
            e_delta[0, 14, 1] += smile * -0.02
            e_delta[0, 17, 1] += smile * 0.0065
            e_delta[0, 17, 2] += smile * 0.003
            e_delta[0, 13, 1] += smile * -0.00275
            e_delta[0, 16, 1] += smile * -0.00275
            e_delta[0, 3, 1] += smile * -0.0035
            e_delta[0, 7, 1] += smile * -0.0035

            # Mouth open (aaa)
            e_delta[0, 19, 1] += mouth * 0.001
            e_delta[0, 19, 2] += mouth * 0.0001
            e_delta[0, 17, 1] += mouth * -0.0001
            r_pitch -= mouth * 0.05

            # Eee
            e_delta[0, 20, 2] += eee_v * -0.001
            e_delta[0, 20, 1] += eee_v * -0.001
            e_delta[0, 14, 1] += eee_v * -0.001

            # Woo
            e_delta[0, 14, 1] += woo_v * 0.001
            e_delta[0, 3, 1] += woo_v * -0.0005
            e_delta[0, 7, 1] += woo_v * -0.0005
            e_delta[0, 17, 2] += woo_v * -0.0005

            # Wink
            e_delta[0, 11, 1] += wink * 0.001
            e_delta[0, 13, 1] += wink * -0.0003
            e_delta[0, 17, 0] += wink * 0.0003
            e_delta[0, 17, 1] += wink * 0.0003
            e_delta[0, 3, 1] += wink * -0.0003
            r_roll -= wink * 0.1
            r_yaw -= wink * 0.1

            # Pupil X
            if pupil_x > 0:
                e_delta[0, 11, 0] += pupil_x * 0.0007
                e_delta[0, 15, 0] += pupil_x * 0.001
            else:
                e_delta[0, 11, 0] += pupil_x * 0.001
                e_delta[0, 15, 0] += pupil_x * 0.0007

            # Pupil Y
            e_delta[0, 11, 1] += pupil_y * -0.001
            e_delta[0, 15, 1] += pupil_y * -0.001
            blink_l -= pupil_y / 2.0
            blink_r -= pupil_y / 2.0

            # Left eye blink (kp 11 = left eye, 13 = left eyelid)
            e_delta[0, 11, 1] += blink_l * -0.001
            e_delta[0, 13, 1] += blink_l * 0.0003
            e_delta[0, 1, 1] += blink_l * -0.00025

            # Right eye blink (kp 15 = right eye, 16 = right eyelid)
            e_delta[0, 15, 1] += blink_r * -0.001
            e_delta[0, 16, 1] += blink_r * 0.0003
            e_delta[0, 2, 1] += blink_r * 0.00025

            # Left eyebrow (kp 1) — matches ALP combined eyebrow code
            if eb_l > 0:
                e_delta[0, 1, 1] += eb_l * 0.001
            else:
                e_delta[0, 1, 0] += eb_l * -0.001
                e_delta[0, 1, 1] += eb_l * 0.0003

            # Right eyebrow (kp 2) — matches ALP combined eyebrow code
            if eb_r > 0:
                e_delta[0, 2, 1] += eb_r * -0.001
            else:
                e_delta[0, 2, 0] += eb_r * 0.001
                e_delta[0, 2, 1] += eb_r * -0.0003

            # ── Build rotation matrix: source + delta (in degrees)
            new_rotate = get_rotation_matrix(
                source_kp_info['pitch'] + r_pitch,
                source_kp_info['yaw'] + r_yaw,
                source_kp_info['roll'] + r_roll,
            )

            # ── Compute driving keypoints ──
            # MUST match _transform_keypoint formula: (kp @ R) + exp * scale + t
            # so that stitching sees compatible source/driving and doesn't fight rotation.
            kp = source_kp_info['kp']
            exp = source_kp_info['exp']
            scale = source_kp_info['scale']
            t = source_kp_info['t']
            bs = kp.shape[0]
            num_kp = kp.shape[1] if kp.ndim == 3 else kp.shape[1] // 3

            kp_driving = (
                kp.view(bs, num_kp, 3) @ new_rotate
                + exp.view(bs, num_kp, 3)
                + e_delta
            )
            kp_driving *= scale[..., None]
            kp_driving[:, :, 0:2] += t[:, None, 0:2]

            # Stitching
            stitching_net = (srm["stitching"]
                            if isinstance(srm, dict) else None)
            kp_driving = _do_stitching(
                stitching_net, source_kp, kp_driving)

            # Warp + decode (returns 512x512 BGR uint8)
            out_img = _warp_decode(
                wn, sg, source_feature_3d, source_kp, kp_driving)

            # Use proper paste_back with 512→frame resolution mapping
            # _paste_back handles M_inv scaling for 512-space and
            # applies soft elliptical mask blending with LANCZOS4
            result = _paste_back(result, out_img, M_inv)
    finally:
        # Offload models
        offload = models["offload_device"]
        for m in (afe, me, wn, sg):
            try:
                m.to(offload)
            except Exception:
                pass
        if isinstance(srm, dict):
            for v in srm.values():
                if hasattr(v, "to"):
                    try:
                        v.to(offload)
                    except Exception:
                        pass

    return result


# ── FacePoke ComfyUI Node ──────────────────────────────────────────────

class FacePokeNode:
    """Per-frame face puppeteering node using LivePortrait.

    Provides inline editing UI with frame scrubber, face dragging,
    and expression sliders. Follows the Video Editor / LoadLastVideo
    patterns for upstream input priority + ExecutionBlocker.

    Input priority: upstream video_path > upstream images > uploaded video.
    """

    CATEGORY = "FFMPEGA"
    FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE", "STRING", "AUDIO", "STRING")
    RETURN_NAMES = ("images", "video_path", "audio", "edit_data")
    OUTPUT_NODE = True

    # Cache for images→video conversions (keyed by node_id)
    _temp_video_cache: dict[str, tuple[str, str]] = {}

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "pause_on_input": ("BOOLEAN", {
                    "default": True,
                    "label_on": "pause & edit",
                    "label_off": "passthrough",
                    "tooltip": (
                        "When ON, pauses the workflow and shows the face "
                        "editor. Click Apply Edits to rebuild and pass "
                        "downstream. When OFF, passes through without editing."
                    ),
                }),
                "auto_open_editor": ("BOOLEAN", {
                    "default": True,
                    "tooltip": (
                        "When ON, the face editor modal auto-opens when "
                        "the workflow pauses. When OFF, click 'Open Face "
                        "Editor' manually."
                    ),
                }),
            },
            "optional": {
                "images": ("IMAGE", {
                    "tooltip": "Video frames as IMAGE tensor batch [N,H,W,3].",
                }),
                "video_path": ("STRING", {
                    "default": "",
                    "forceInput": True,
                    "tooltip": "Path to a video file on disk. "
                               "Upstream connections always win over uploaded video.",
                }),
                "audio": ("AUDIO", {
                    "tooltip": "Audio track to associate with the video.",
                }),
                "fps": ("FLOAT", {
                    "default": 0.0,
                    "min": 0.0, "max": 120.0, "step": 0.01,
                    "forceInput": True,
                    "tooltip": "Framerate for IMAGE tensor input. "
                               "0 = auto-detect from source.",
                }),
                "edit_data": ("STRING", {
                    "default": "",
                    "forceInput": True,
                    "tooltip": "Pre-existing edit JSON to resume from "
                               "(output from a previous FacePoke run).",
                }),
            },
            "hidden": {
                "_edit_action": ("STRING", {"default": "none"}),
                "unique_id": "UNIQUE_ID",
            },
        }

    @classmethod
    def IS_CHANGED(cls, pause_on_input=True, _edit_action="none", **kwargs):
        if not pause_on_input:
            return ""  # passthrough never re-runs on its own
        m = hashlib.sha256()
        m.update(str(_edit_action).encode())
        m.update(str(time.time()).encode())
        return m.hexdigest()

    @classmethod
    def VALIDATE_INPUTS(cls, **kwargs):
        fps_val = kwargs.get("fps", 0.0)
        if fps_val is not None and fps_val != "":
            try:
                float(fps_val)
            except (ValueError, TypeError):
                return f"Invalid fps value: {fps_val}"
        return True

    def execute(
        self,
        pause_on_input: bool = True,
        images=None,
        video_path: str = "",
        audio=None,
        fps: float = 0.0,
        edit_data: str = "",
        _edit_action: str = "none",
        unique_id=None,
        **kwargs,
    ):
        """Execute the FacePoke node.

        Flow:
        1. Resolve video source (priority: video_path > images > uploaded)
        2. Passthrough mode: skip editing, pass video unchanged
        3. Pause mode + no edits: show editor UI, return ExecutionBlocker
        4. Pause mode + has edits: rebuild video with modified frames
        """
        # Defensive cast — fps may arrive as "" from an unconnected widget
        try:
            fps = float(fps) if fps is not None and fps != "" else 0.0
        except (ValueError, TypeError):
            fps = 0.0

        folder_paths = _get_folder_paths()
        empty_frames = torch.zeros(1, 512, 512, 3)
        silent_audio = {"waveform": torch.zeros(1, 1, 1), "sample_rate": 44100}

        # ── Resolve video source (priority: video_path > images) ──
        resolved_path = None

        if video_path and video_path.strip():
            vp = video_path.strip()
            if images is not None:
                logger.info("[FacePoke] Both video_path and images connected "
                            "— using video_path")
            if not self._is_path_sandboxed(vp):
                logger.warning("[FacePoke] video_path '%s' outside allowed "
                               "directories, ignoring", vp)
            elif os.path.isfile(vp):
                resolved_path = vp
                logger.info("[FacePoke] using upstream video_path: %s", vp)
            else:
                logger.warning("[FacePoke] video_path not found: %s", vp)

        if resolved_path is None and images is not None:
            resolved_path = self._resolve_images_input(
                images, fps, unique_id, folder_paths)

        if resolved_path is None:
            logger.info("[FacePoke] No input connected")
            return {
                "ui": {"text": ["Connect a video path, IMAGE tensor, "
                                "or upload a video"]},
                "result": (empty_frames, "", silent_audio, ""),
            }

        # ── Extract audio from video if no upstream audio ──
        if audio is None and resolved_path:
            audio = self._extract_audio(resolved_path)
        if audio is None:
            audio = silent_audio

        # ── Get video metadata ──
        cap = cv2.VideoCapture(resolved_path)
        actual_fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        cap.release()

        # ── Passthrough mode: skip editing ──
        if not pause_on_input:
            frames = self._load_frames(resolved_path)
            return {
                "ui": {"video_path": [resolved_path]},
                "result": (frames, resolved_path, audio, ""),
            }

        # ── Check for server-side edits (from Apply Edits button) ──
        node_id = str(unique_id) if unique_id else ""
        server_edits = None
        state = _facepoke_edit_states.pop(node_id, None)
        if state and state.get("data"):
            server_edits = state["data"]
            logger.info("[FacePoke] Found server-side edits for node %s "
                        "(%d frames)", node_id,
                        len(server_edits) if isinstance(server_edits, dict)
                        else 0)

        # ── Check for widget-based edit_data (from previous run) ──
        widget_edits = None
        if edit_data and edit_data.strip():
            try:
                parsed = json.loads(edit_data)
                if isinstance(parsed, dict) and parsed:
                    widget_edits = parsed
            except json.JSONDecodeError:
                logger.warning("[FacePoke] Invalid edit_data JSON")

        edits = server_edits or widget_edits

        if edits and (server_edits is not None
                      or _edit_action == "passthrough"):
            # Rebuild video with edits applied
            output_path = self._rebuild_video(resolved_path, edits)
            edit_json = json.dumps(edits)
            frames = self._load_frames(output_path)

            return {
                "ui": {"video_path": [output_path]},
                "result": (frames, output_path, audio, edit_json),
            }

        # ── First run: show editor UI and pause ──
        logger.info("[FacePoke] Pausing — waiting for face editing")

        try:
            from comfy_execution.graph import ExecutionBlocker
            blocked = ExecutionBlocker(None)

            return {
                "ui": {
                    "video_path": [resolved_path],
                    "facepoke_meta": [{
                        "video_path": resolved_path,
                        "total_frames": total_frames,
                        "fps": actual_fps,
                        "width": width,
                        "height": height,
                        "edit_data": edit_data or "{}",
                    }],
                },
                "result": tuple(blocked for _ in range(4)),
            }
        except ImportError:
            logger.warning(
                "[FacePoke] ExecutionBlocker not available — "
                "requires ComfyUI 0.1.3+. Passing through.")
            frames = self._load_frames(resolved_path)
            return {
                "result": (frames, resolved_path, audio,
                           edit_data or "{}"),
            }

    # ─── Private helpers ────────────────────────────────────────────

    def _resolve_images_input(
        self,
        images: torch.Tensor,
        fps: float,
        unique_id,
        folder_paths,
    ) -> str | None:
        """Convert IMAGE tensor to a temp video file."""
        try:
            temp_dir = (folder_paths.get_temp_directory()
                        if folder_paths else "/tmp")
            os.makedirs(temp_dir, exist_ok=True)

            cache_key = str(unique_id) if unique_id else "default"
            content_hash = self._tensor_content_hash(images)

            # Check cache — invalidate if tensor content changed
            cached = self._temp_video_cache.get(cache_key)
            if cached:
                cached_path, cached_hash = cached
                if cached_hash == content_hash and os.path.isfile(cached_path):
                    return cached_path
                try:
                    os.unlink(cached_path)
                except OSError:
                    pass

            _fd, temp_path = tempfile.mkstemp(
                prefix="facepoke_", suffix=".mp4", dir=temp_dir)
            os.close(_fd)

            self._images_to_video(
                images, temp_path, fps=int(fps) if fps > 0 else 24)
            self._temp_video_cache[cache_key] = (temp_path, content_hash)
            return temp_path

        except Exception as e:
            logger.warning("[FacePoke] Failed to convert images: %s", e)
            return None

    @staticmethod
    def _tensor_content_hash(images: torch.Tensor) -> str:
        """Compute a lightweight hash of tensor shape + sampled content."""
        m = hashlib.sha256()
        m.update(str(images.shape).encode())
        m.update(images[0, :4, :4, :].cpu().numpy().tobytes())
        if images.shape[0] > 1:
            m.update(images[-1, :4, :4, :].cpu().numpy().tobytes())
        return m.hexdigest()

    @staticmethod
    def _images_to_video(
        images: torch.Tensor, output_path: str, fps: int = 24,
    ) -> None:
        """Stream IMAGE tensor frames to FFmpeg → temp video."""
        try:
            from ..core.images_to_video import images_to_video
        except ImportError:
            from core.images_to_video import images_to_video  # type: ignore
        images_to_video(images, output_path, fps=fps)

    @staticmethod
    def _extract_audio(video_path: str) -> dict | None:
        """Extract audio from a video file as a ComfyUI AUDIO dict."""
        try:
            from ..core.bin_paths import get_ffmpeg_bin, get_ffprobe_bin
        except ImportError:
            try:
                from core.bin_paths import get_ffmpeg_bin, get_ffprobe_bin  # type: ignore
            except ImportError:
                return None

        ffprobe = get_ffprobe_bin()
        ffmpeg = get_ffmpeg_bin()
        if not ffprobe or not ffmpeg:
            return None

        channels = 2
        sample_rate = 44100

        # Check if video has audio
        try:
            probe = subprocess.run(
                [
                    ffprobe, "-v", "quiet",
                    "-select_streams", "a:0",
                    "-show_entries", "stream=codec_type",
                    "-of", "csv=p=0",
                    video_path,
                ],
                capture_output=True, text=True, timeout=10,
            )
            if probe.returncode != 0 or "audio" not in probe.stdout:
                return None
        except Exception:
            return None

        # Extract audio to WAV via ffmpeg
        try:
            result = subprocess.run(
                [
                    ffmpeg, "-i", video_path,
                    "-vn", "-f", "wav",
                    "-acodec", "pcm_s16le",
                    "-ac", str(channels),
                    "-ar", str(sample_rate),
                    "pipe:1",
                ],
                capture_output=True, timeout=30,
            )
            if result.returncode != 0 or not result.stdout:
                return None

            import struct
            data = result.stdout
            if len(data) <= 44:
                return None

            idx = data.find(b'data', 12)
            if idx < 0:
                return None
            data_size = struct.unpack_from('<I', data, idx + 4)[0]
            pcm_start = idx + 8
            available = len(data) - pcm_start
            if available <= 0:
                return None
            if data_size > available:
                data_size = available
            pcm_bytes = data[pcm_start:pcm_start + data_size]

            samples = np.frombuffer(
                pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
            remainder = len(samples) % channels
            if remainder:
                samples = samples[:-remainder]
            if len(samples) == 0:
                return None
            samples = samples.reshape(-1, channels).T
            waveform = torch.from_numpy(samples).unsqueeze(0)

            return {"waveform": waveform, "sample_rate": sample_rate}
        except Exception as e:
            logger.warning("[FacePoke] Audio extraction failed: %s", e)
            return None

    def _load_frames(self, video_path: str) -> torch.Tensor:
        """Load all frames from a video as a normalized tensor."""
        cap = cv2.VideoCapture(video_path)
        frames = []
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            frames.append(
                torch.from_numpy(rgb).float() / 255.0)
        cap.release()

        if not frames:
            return torch.zeros(1, 64, 64, 3)

        return torch.stack(frames)

    @torch.no_grad()
    def _rebuild_video(
        self,
        video_path: str,
        edits: dict,
    ) -> str:
        """Rebuild video with LivePortrait edits on specified frames.

        Only edited frames are re-rendered; untouched frames pass through.
        """
        logger.info("[FacePoke] Rebuilding video with %d edited frames",
                    len(edits))

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise RuntimeError(f"Cannot open video: {video_path}")

        fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        folder_paths = _get_folder_paths()
        out_dir = (folder_paths.get_temp_directory()
                   if folder_paths else tempfile.mkdtemp(prefix="ffmpega_fp_"))
        os.makedirs(out_dir, exist_ok=True)
        base = os.path.splitext(os.path.basename(video_path))[0]
        out_path = os.path.join(out_dir, f"{base}_facepoke.mp4")

        fourcc = cv2.VideoWriter.fourcc(*"mp4v")
        writer = cv2.VideoWriter(out_path, fourcc, fps, (width, height))

        edited_frame_indices = set()
        for k in edits:
            try:
                edited_frame_indices.add(int(k))
            except (ValueError, TypeError):
                pass

        frame_idx = 0
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            if frame_idx in edited_frame_indices:
                frame_edits = edits.get(str(frame_idx), {})
                if frame_edits:
                    try:
                        frame = _apply_face_edits(frame, frame_edits)
                    except Exception as e:
                        logger.warning(
                            "[FacePoke] Frame %d edit failed: %s",
                            frame_idx, e)

            writer.write(frame)
            frame_idx += 1

        writer.release()
        cap.release()

        # Re-mux with audio from original
        try:
            from ..core.bin_paths import get_ffmpeg_bin
            ffmpeg = get_ffmpeg_bin()
        except ImportError:
            try:
                from core.bin_paths import get_ffmpeg_bin  # type: ignore
                ffmpeg = get_ffmpeg_bin()
            except ImportError:
                ffmpeg = "ffmpeg"

        final_path = os.path.join(out_dir, f"{base}_facepoke_final.mp4")
        cmd = [
            ffmpeg, "-y",
            "-i", out_path,       # video with edits
            "-i", video_path,     # original (for audio)
            "-c:v", "libx264",
            "-crf", "18",
            "-preset", "fast",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "192k",
            "-map", "0:v:0",
            "-map", "1:a:0?",
            "-shortest",
            final_path,
        ]
        try:
            subprocess.run(cmd, capture_output=True, timeout=300)
            if os.path.isfile(final_path):
                os.remove(out_path)
                return final_path
        except Exception as e:
            logger.warning("[FacePoke] FFmpeg remux failed: %s", e)

        return out_path

    @staticmethod
    def _is_path_sandboxed(path: str) -> bool:
        """Check if a path is within ComfyUI's or system temp directories."""
        try:
            from ..loadlast.discovery.path_utils import is_path_sandboxed
            if is_path_sandboxed(path):
                return True
        except ImportError:
            pass

        real = os.path.realpath(path)
        sys_tmp = os.path.realpath(tempfile.gettempdir())
        return real == sys_tmp or real.startswith(sys_tmp + os.sep)


# Clean up temp video files on process exit
def _cleanup_temp_video_cache():
    for path, _hash in list(FacePokeNode._temp_video_cache.values()):
        try:
            os.unlink(path)
        except OSError:
            pass
    FacePokeNode._temp_video_cache.clear()


atexit.register(_cleanup_temp_video_cache)
