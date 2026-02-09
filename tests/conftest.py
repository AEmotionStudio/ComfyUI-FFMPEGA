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
    sys.modules["folder_paths"] = mock_fp
