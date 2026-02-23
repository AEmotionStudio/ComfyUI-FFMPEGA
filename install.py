"""Auto-install script for ComfyUI Manager.

ComfyUI Manager runs this file automatically when installing the node.
We use --no-deps for packages that have overly restrictive version pins
that would otherwise break ComfyUI's environment.
"""

import subprocess
import sys
import importlib

pip = [sys.executable, "-m", "pip", "install", "--quiet"]


def is_installed(package_name: str) -> bool:
    """Check if a package is already installed."""
    try:
        importlib.import_module(package_name)
        return True
    except ImportError:
        return False


def main():
    print("[FFMPEGA] Installing optional dependencies...")

    # --- SAM3 (object segmentation for auto_mask) ---
    if not is_installed("sam2"):
        print("[FFMPEGA] Installing SAM3 (--no-deps to avoid numpy conflicts)...")
        result = subprocess.run(
            [*pip, "--no-deps", "git+https://github.com/facebookresearch/sam3.git"],
        )
        if result.returncode == 0:
            print("[FFMPEGA] ✓ SAM3 installed successfully")
        else:
            print("[FFMPEGA] ✗ SAM3 installation failed — auto_mask will use fallback")
    else:
        print("[FFMPEGA] ✓ SAM3 already installed")

    print("[FFMPEGA] Dependency installation complete")


if __name__ == "__main__":
    main()
else:
    # ComfyUI Manager imports this file — run main() on import
    main()
