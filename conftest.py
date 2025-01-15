"""Root conftest.py - configure pytest for standalone testing outside ComfyUI.

The root __init__.py has `from .nodes import ...` which requires ComfyUI runtime.
We prevent it from being imported by pre-registering the root package as a dummy
module in sys.modules before any test imports happen.
"""

import sys
import os
import types

project_root = os.path.dirname(os.path.abspath(__file__))
root_pkg_name = os.path.basename(project_root)

# Add project root to sys.path so `core`, `skills`, etc. are importable
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# ── Pre-register a dummy root package to prevent __init__.py from loading ──
# Without this, `from core.sanitize import ...` causes Python to resolve `core`
# as a sub-package of the root (because root has __init__.py), which triggers
# `from .nodes import NODE_CLASS_MAPPINGS` and fails outside ComfyUI.
#
# By registering the root package name as a dummy module already in sys.modules,
# Python won't try to import __init__.py when resolving sub-packages.
if root_pkg_name not in sys.modules:
    dummy = types.ModuleType(root_pkg_name)
    dummy.__path__ = [project_root]
    dummy.__file__ = os.path.join(project_root, "__init__.py")
    sys.modules[root_pkg_name] = dummy

# Create a mock for folder_paths (ComfyUI-specific module)
if "folder_paths" not in sys.modules:
    mock_fp = types.ModuleType("folder_paths")
    mock_fp.get_output_directory = lambda: "/tmp/comfyui_output"
    sys.modules["folder_paths"] = mock_fp

# Prevent pytest from collecting these files as tests
collect_ignore = [
    os.path.join(project_root, "__init__.py"),
    os.path.join(project_root, "nodes.py"),
]
