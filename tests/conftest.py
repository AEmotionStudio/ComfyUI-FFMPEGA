"""Pytest configuration for ComfyUI-FFMPEGA tests.

Sets up sys.path so that both direct package imports (e.g. `from skills.registry import ...`)
and relative imports within the package (e.g. `from ..core import ...`) work correctly
when running pytest from the project root.
"""

import sys
import os
import types

# Add project root to sys.path so `skills`, `core`, `nodes`, `prompts` are importable
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Create a mock for folder_paths (ComfyUI-specific module)
if "folder_paths" not in sys.modules:
    mock_fp = types.ModuleType("folder_paths")
    mock_fp.get_output_directory = lambda: "/tmp/comfyui_output"
    mock_fp.get_temp_directory = lambda: "/tmp/comfyui_temp"
    mock_fp.get_input_directory = lambda: "/tmp/comfyui_input"
    mock_fp.get_annotated_filepath = lambda v: "/tmp/comfyui_input/" + v if v else ""
    mock_fp.exists_annotated_filepath = lambda v: True
    mock_fp.filter_files_content_types = lambda files, types: files
    mock_fp.get_save_image_path = lambda prefix, output_dir, *a, **kw: (
        output_dir, prefix, 1, "", ""
    )
    from _comfy_stubs import install_model_folders
    install_model_folders(mock_fp)
    sys.modules["folder_paths"] = mock_fp

# --------------------------------------------------------------------------
# Skip torch-dependent test files when torch is not installed (CI).
# These files import from nodes/ which requires torch at module level.
# --------------------------------------------------------------------------
try:
    import torch  # noqa: F401
except ImportError:
    collect_ignore_glob = [
        # Tests that import from nodes/ — all node modules require torch
        "test_ace_step.py",
        "test_ai_upscale.py",
        "test_audio_inpaint.py",
        "test_depth_shader.py",
        "test_dreamid_omni.py",
        "test_effects_node.py",
        "test_facecam.py",
        "test_flux_klein.py",
        "test_frame_picker.py",
        "test_generate_audio.py",
        "test_generate_music.py",
        "test_kiwi_edit.py",
        "test_lip_sync.py",
        "test_matanyone2.py",
        "test_media_bridge.py",
        "test_minimax_remover.py",
        "test_node_chaining.py",
        "test_phase5_model_config.py",
        "test_rembg.py",
        "test_save_video_node.py",
        "test_shader.py",
        "test_svi.py",
    ]

