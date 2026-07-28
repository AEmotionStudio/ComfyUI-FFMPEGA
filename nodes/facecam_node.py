# coding: utf-8
"""FaceCam ComfyUI node — portrait video camera control.

Uses 2+2 architecture:
  model_high + model_low = Base Wan2.2 GGUF models (via "Load Diffusion Model")
  facecam_high + facecam_low = FaceCam bf16 partial checkpoints (auto-loaded)

FaceCam checkpoints are PARTIAL fine-tunes of Wan2.2-I2V-A14B.
They contain self-attention + patch_embedding layers (402 keys).
They are auto-downloaded from AEmotionStudio/facecam-wan2.2-14b-bf16
on first use and applied as direct weight replacements at runtime.
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path

import numpy as np

log = logging.getLogger("ffmpega")

# HuggingFace repo containing pre-merged FaceCam checkpoints
_HF_REPO = "AEmotionStudio/facecam-wan2.2-14b-bf16"
_FACECAM_FILES = {
    "high": "facecam_wan2.2_14b_high_bf16.safetensors",
    "low": "facecam_wan2.2_14b_low_bf16.safetensors",
    "gaussians": "gaussians.ply",
    "landmarker": "face_landmarker_v2_with_blendshapes.task",
}


class FaceCamNode:
    """ComfyUI node for FaceCam — portrait camera control."""

    CATEGORY = "FFMPEGA"
    FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE", "STRING", "LATENT")
    RETURN_NAMES = ("images", "video_path", "latent")
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls):
        try:
            from ..core.facecam_synthesizer import CAMERA_PRESETS
        except ImportError:
            try:
                from core.facecam_synthesizer import CAMERA_PRESETS
            except ImportError:
                CAMERA_PRESETS = {
                    "orbit_left": None, "orbit_right": None,
                    "zoom_in": None, "zoom_out": None,
                    "look_up": None, "look_down": None,
                    "dramatic_pan": None, "subtle_drift": None,
                    "dolly_zoom": None, "random": None,
                }

        preset_list = list(CAMERA_PRESETS.keys()) + ["custom"]

        return {
            "required": {
                "model_high": ("MODEL", {
                    "tooltip": "Wan2.2 base model (high-noise)",
                }),
                # --- Prompts (top) ---
                "prompt": ("STRING", {
                    "default": "A portrait of a person",
                    "multiline": True,
                }),
                "negative_prompt": ("STRING", {
                    "default": "",
                    "multiline": True,
                }),
                # --- Sampler controls ---
                "seed": ("INT", {
                    "default": 0, "min": 0, "max": 0xFFFFFFFF,
                }),
                "steps": ("INT", {
                    "default": 50, "min": 1, "max": 200, "step": 1,
                }),
                "cfg_scale": ("FLOAT", {
                    "default": 5.0, "min": 1.0, "max": 20.0, "step": 0.5,
                }),
                "sampler_name": (
                    ["euler", "euler_ancestral", "dpmpp_2m", "dpmpp_sde"],
                    {"default": "euler"},
                ),
                "scheduler": (
                    ["simple", "normal", "karras", "sgm_uniform"],
                    {"default": "simple"},
                ),
                # --- Model switch ratio ---
                "high_model_ratio": ("FLOAT", {
                    "default": 0.2, "min": 0.0, "max": 1.0, "step": 0.05,
                    "tooltip": (
                        "Fraction of steps using HIGH model (camera trajectory). "
                        "Remaining steps use LOW model (detail refinement). "
                        "0=all LOW, 1=all HIGH."
                    ),
                }),
                # --- Camera preset ---
                "camera_preset": (preset_list, {
                    "default": "orbit_left",
                    "tooltip": (
                        "Camera motion preset. Every preset starts at the input pose (frontal) "
                        "and moves outward, matching what FaceCam was trained on: "
                        "'orbit_left' = camera swings left (az 0→-45°). "
                        "'orbit_right' = swings right (az 0→+45°). "
                        "'zoom_in' = pushes in tight (FOV 50→25°). "
                        "'zoom_out' = pulls back wide (FOV 25→50°). "
                        "'look_up' = subject looks up (elev 0→-30°). "
                        "'look_down' = subject looks down (elev 0→+30°). "
                        "'dramatic_pan' = orbit 0→45° + tilt + zoom tightening. "
                        "'subtle_drift' = gentle orbit 0→15° + tilt 0→-8° (most natural). "
                        "'dolly_zoom' = orbit 0→25° while zooming in (Hitchcock effect). "
                        "'random' = randomized direction, up to 45° from frontal. "
                        "'custom' = use the manual azimuth/elevation/FOV sliders below. "
                        "Note: sweeps beyond ~45° push the face into profile, where the "
                        "landmark tracker loses the mesh and camera control weakens."
                    ),
                }),
                # --- Dimensions ---
                "num_frames": ("INT", {
                    "default": 81, "min": 5, "max": 321, "step": 4,
                }),
                "width": ("INT", {
                    "default": 480, "min": 128, "max": 1920, "step": 8,
                    "tooltip": "FaceCam is trained on portrait video — upstream "
                               "defaults to 480×704 (w×h). Landscape is "
                               "off-distribution and weakens camera control.",
                }),
                "height": ("INT", {
                    "default": 704, "min": 128, "max": 1920, "step": 8,
                    "tooltip": "FaceCam is trained on portrait video — upstream "
                               "defaults to 480×704 (w×h).",
                }),
            },
            "optional": {
                "images": ("IMAGE", {
                    "tooltip": "Input image/frames (alternative to video_path)",
                }),
                "video_path": ("STRING", {
                    "forceInput": True,
                    "tooltip": "Input video path (connect from LoadVideoPath node)",
                }),
                "model_low": ("MODEL", {
                    "tooltip": "Wan2.2 base model (low-noise) for refinement pass. "
                               "If not connected, HIGH model runs all steps.",
                }),
                "vae": ("VAE", {
                    "tooltip": "Wan 2.2 VAE",
                }),
                "clip": ("CLIP", {
                    "tooltip": "T5-XXL text encoder",
                }),
                # Camera overrides (used when camera_preset = "custom")
                "start_azimuth": ("FLOAT", {
                    "default": 0, "min": -90, "max": 90, "step": 1,
                    "tooltip": "Horizontal rotation start. Negative=camera left, positive=right.",
                }),
                "end_azimuth": ("FLOAT", {
                    "default": 0, "min": -90, "max": 90, "step": 1,
                    "tooltip": "Horizontal rotation end.",
                }),
                "start_elevation": ("FLOAT", {
                    "default": 0, "min": -60, "max": 60, "step": 1,
                    "tooltip": "Vertical rotation start. Positive=looking down, negative=looking up.",
                }),
                "end_elevation": ("FLOAT", {
                    "default": 0, "min": -60, "max": 60, "step": 1,
                    "tooltip": "Vertical rotation end.",
                }),
                "start_fov": ("FLOAT", {
                    "default": 40, "min": 10, "max": 60, "step": 1,
                    "tooltip": "Field of view start. Higher=wider (zoom out), lower=tighter (zoom in).",
                }),
                "end_fov": ("FLOAT", {
                    "default": 40, "min": 10, "max": 60, "step": 1,
                    "tooltip": "Field of view end.",
                }),
                "mesh_source": (
                    ["auto", "analytic", "detected"],
                    {
                        "default": "auto",
                        "tooltip": "How camera conditioning is built. "
                                   "'auto' (recommended) poses MediaPipe's canonical face "
                                   "model with the camera matrices directly — total coverage, "
                                   "perfectly smooth motion, and left/right orbits are exact "
                                   "mirrors. Falls back to detection if calibration fails. "
                                   "'analytic' forces projection and errors if it can't calibrate. "
                                   "'detected' uses the old path: render a 3D proxy head and "
                                   "run a face detector over it, which loses the mesh past ~45° "
                                   "and has to interpolate the gaps.",
                    },
                ),
                "blockswap_blocks": ("INT", {
                    "default": 0,
                    "min": 0,
                    "max": 40,
                    "step": 1,
                    "tooltip": "BlockSwap: number of Wan2.2 DiT blocks (of 40) to keep off-GPU "
                               "during sampling, cast back per-layer on forward. "
                               "0 = disabled (keep everything on GPU, recommended for ≥24 GB VRAM). "
                               "8-16 = for 12-16 GB cards. 20+ = for 8-12 GB cards. "
                               "FaceCam doubles the temporal dimension, so it needs noticeably "
                               "more VRAM than a plain Wan2.2 run at the same resolution. "
                               "Higher values trade speed for headroom.",
                }),
                "allow_model_downloads": ("BOOLEAN", {
                    "default": True,
                    "label_on": "Downloads On",
                    "label_off": "Downloads Off",
                    "tooltip": (
                        "Auto-download FaceCam checkpoints (~16.8 GB) from HuggingFace on first use. "
                        "Turn Off to prevent downloads — you must manually place models in "
                        "ComfyUI/models/diffusion_models/."
                    ),
                }),
            },
        }

    def execute(
        self,
        model_high,
        camera_preset: str = "orbit_left",
        prompt: str = "A portrait of a person",
        negative_prompt: str = "",
        num_frames: int = 81,
        width: int = 480,
        height: int = 704,
        high_model_ratio: float = 0.2,
        # Optional
        images=None,
        vae=None,
        clip=None,
        video_path: str = "",
        model_low=None,
        start_azimuth: float = 0,
        end_azimuth: float = 0,
        start_elevation: float = 0,
        end_elevation: float = 0,
        start_fov: float = 40,
        end_fov: float = 40,
        cfg_scale: float = 5.0,
        steps: int = 50,
        seed: int = 0,
        sampler_name: str = "euler",
        scheduler: str = "simple",
        mesh_source: str = "auto",
        blockswap_blocks: int = 0,
        allow_model_downloads: bool = True,
    ):
        import torch
        try:
            from ..core.facecam_synthesizer import (
                generate_facecam_video,
                resolve_camera_params,
                load_video_frames,
            )
        except ImportError:
            from core.facecam_synthesizer import (  # type: ignore
                generate_facecam_video,
                resolve_camera_params,
                load_video_frames,
            )

        # Auto-resolve FaceCam checkpoints (download if needed)
        facecam_high_path, facecam_low_path = self._ensure_facecam_models(
            allow_model_downloads, need_low=(model_low is not None),
        )

        # Load input frames
        input_frames = self._resolve_input_frames(
            images, video_path, num_frames, height, width,
        )

        # Resolve camera params
        if camera_preset != "custom":
            camera_params = resolve_camera_params(preset=camera_preset)
        else:
            camera_params = resolve_camera_params(
                start_azimuth=start_azimuth,
                end_azimuth=end_azimuth,
                start_elevation=start_elevation,
                end_elevation=end_elevation,
                start_fov=start_fov,
                end_fov=end_fov,
            )

        log.info(
            "[FaceCam] Camera: preset=%s, params=%s",
            camera_preset, camera_params,
        )

        # Output path
        timestamp = int(time.time())
        try:
            comfy_root = Path(__file__).resolve().parents[2]
            out_dir = comfy_root / "output"
        except Exception:
            out_dir = Path.home() / "ComfyUI" / "output"
        out_dir.mkdir(parents=True, exist_ok=True)
        output_path = str(out_dir / f"facecam_{timestamp}.mp4")

        output_path, latent_output = generate_facecam_video(
            input_frames=input_frames,
            wan_high_patcher=model_high,
            facecam_high_path=facecam_high_path,
            wan_low_patcher=model_low,
            facecam_low_path=facecam_low_path,
            vae=vae,
            clip=clip,
            camera_params=camera_params,
            output_path=output_path,
            num_frames=num_frames,
            height=height,
            width=width,
            cfg_scale=cfg_scale,
            num_steps=steps,
            sampler_name=sampler_name,
            scheduler=scheduler,
            seed=seed,
            prompt=prompt,
            negative_prompt=negative_prompt,
            high_model_ratio=high_model_ratio,
            blockswap_blocks=blockswap_blocks,
            mesh_source=mesh_source,
        )

        # Load output as images for ComfyUI
        try:
            try:
                from ..core.facecam_synthesizer import load_video_frames as lvf
            except ImportError:
                from core.facecam_synthesizer import load_video_frames as lvf  # type: ignore
            out_frames, _ = lvf(output_path, max_frames=num_frames)
            frames_tensor = torch.stack([
                torch.from_numpy(f).float() / 255.0 for f in out_frames
            ])
        except Exception as e:
            log.warning("[FaceCam] Could not load output as images: %s", e)
            frames_tensor = torch.zeros(1, height, width, 3)

        # Build LATENT dict (or empty if sampling failed)
        if latent_output is None:
            latent_output = {"samples": torch.zeros(1, 16, 1, 1, 1)}

        return (frames_tensor, output_path, latent_output)

    def _ensure_facecam_models(
        self, allow_downloads: bool, need_low: bool = True,
    ) -> tuple[str, str | None]:
        """Ensure FaceCam checkpoints exist, downloading if needed.

        Returns (high_path, low_path). low_path is None if need_low is False.
        """
        try:
            import folder_paths  # type: ignore[import-not-found]
            model_dirs = list(folder_paths.get_folder_paths("diffusion_models"))
        except ImportError:
            model_dirs = [str(Path.home() / "ComfyUI" / "models" / "diffusion_models")]

        # Also accept checkpoints sitting next to gaussians.ply in models/facecam/,
        # which is where users naturally put them. Searched last so downloads still
        # land in diffusion_models (model_dirs[0]).
        try:
            from ..core.facecam_synthesizer import _get_facecam_dir  # type: ignore
        except ImportError:
            from core.facecam_synthesizer import _get_facecam_dir  # type: ignore
        model_dirs.append(str(_get_facecam_dir()))

        # Resolve existing files
        high_name = _FACECAM_FILES["high"]
        low_name = _FACECAM_FILES["low"]

        high_path = self._find_model(model_dirs, high_name)
        low_path = self._find_model(model_dirs, low_name) if need_low else None

        # Download missing files
        need_high = high_path is None
        need_low_dl = need_low and low_path is None

        if need_high or need_low_dl:
            if not allow_downloads:
                try:
                    from ..core import model_manager  # type: ignore[import-not-found]
                except ImportError:
                    from core import model_manager  # type: ignore
                model_manager.set_downloads_allowed(False)
                model_manager.require_downloads_allowed("facecam")

            # Download to first writable model directory
            dl_dir = model_dirs[0]
            os.makedirs(dl_dir, exist_ok=True)

            try:
                from huggingface_hub import hf_hub_download
            except ImportError:
                raise RuntimeError(
                    "huggingface_hub not installed. Run: pip install huggingface_hub"
                )

            if need_high:
                log.info("[FaceCam] Downloading %s from %s...", high_name, _HF_REPO)
                high_path = hf_hub_download(
                    repo_id=_HF_REPO, filename=high_name, local_dir=dl_dir,
                )
                log.info("[FaceCam] ✅ Downloaded: %s", high_path)

            if need_low_dl:
                log.info("[FaceCam] Downloading %s from %s...", low_name, _HF_REPO)
                low_path = hf_hub_download(
                    repo_id=_HF_REPO, filename=low_name, local_dir=dl_dir,
                )
                log.info("[FaceCam] ✅ Downloaded: %s", low_path)

            # Also ensure gaussians.ply and landmarker exist
            self._ensure_facecam_assets(dl_dir)

        return (high_path, low_path)

    @staticmethod
    def _find_model(model_dirs: list[str], filename: str) -> str | None:
        """Find a model file in ComfyUI model directories."""
        for d in model_dirs:
            candidate = Path(d) / filename
            if candidate.is_file():
                return str(candidate)
        return None

    @staticmethod
    def _ensure_facecam_assets(dl_dir: str) -> None:
        """Download gaussians.ply and face_landmarker if missing."""
        try:
            from ..core.facecam_synthesizer import _get_facecam_dir  # type: ignore
        except ImportError:
            from core.facecam_synthesizer import _get_facecam_dir  # type: ignore

        facecam_dir = _get_facecam_dir()

        ply_path = facecam_dir / "gaussians.ply"
        if not ply_path.exists():
            try:
                from huggingface_hub import hf_hub_download
                log.info("[FaceCam] Downloading gaussians.ply...")
                local = hf_hub_download(
                    repo_id=_HF_REPO, filename=_FACECAM_FILES["gaussians"],
                )
                import shutil
                shutil.copy2(local, str(ply_path))
                log.info("[FaceCam] ✅ Saved: %s", ply_path)
            except Exception as e:
                log.warning("[FaceCam] Could not download gaussians.ply: %s", e)

        landmarker_path = facecam_dir / _FACECAM_FILES["landmarker"]
        if not landmarker_path.exists():
            try:
                from huggingface_hub import hf_hub_download
                log.info("[FaceCam] Downloading face_landmarker...")
                local = hf_hub_download(
                    repo_id=_HF_REPO, filename=_FACECAM_FILES["landmarker"],
                )
                import shutil
                shutil.copy2(local, str(landmarker_path))
                log.info("[FaceCam] ✅ Saved: %s", landmarker_path)
            except Exception as e:
                log.warning("[FaceCam] Could not download face_landmarker: %s", e)

    def _resolve_input_frames(
        self, images, video_path, num_frames, height, width,
    ) -> list[np.ndarray]:
        """Resolve input from either IMAGE tensor or video_path."""
        import torch

        if images is not None and images.shape[0] > 0:
            frames = []
            for i in range(min(images.shape[0], num_frames)):
                frame = images[i]
                if frame.dtype == torch.float32:
                    frame = (frame.clamp(0, 1) * 255).byte()
                frames.append(frame.cpu().numpy())

            while len(frames) < num_frames:
                frames.append(frames[-1])
            return frames[:num_frames]

        if video_path and video_path.strip():
            resolved = self._resolve_video_path(video_path.strip())
            try:
                from ..core.facecam_synthesizer import load_video_frames
            except ImportError:
                from core.facecam_synthesizer import load_video_frames  # type: ignore
            frames, fps = load_video_frames(
                resolved, max_frames=num_frames,
                target_height=height, target_width=width,
            )
            log.info(
                "[FaceCam] Loading from video_path: %s | %dx%d | %.1ffps | %d frames",
                resolved, width, height, fps, len(frames),
            )
            return frames

        raise ValueError(
            "FaceCam requires either 'images' or 'video_path' input"
        )

    @staticmethod
    def _resolve_video_path(path: str) -> str:
        """Resolve video path, checking ComfyUI input directory."""
        if os.path.isfile(path):
            return path

        try:
            comfy_root = Path(__file__).resolve().parents[2]
            candidate = comfy_root / "input" / os.path.basename(path)
            if candidate.is_file():
                return str(candidate)
        except Exception:
            pass

        raise FileNotFoundError(f"Video not found: {path}")
