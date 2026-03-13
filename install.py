"""Auto-install script for ComfyUI Manager.

ComfyUI Manager runs this file automatically when installing the node.
We use --no-deps for packages that have overly restrictive version pins
that would otherwise break ComfyUI's environment.
"""

import subprocess
import sys
from importlib.metadata import PackageNotFoundError, distribution

pip = [sys.executable, "-m", "pip", "install", "--quiet"]


def is_installed(dist_name: str) -> bool:
    """Check if a pip distribution is installed (by metadata, not import).

    Using importlib.metadata avoids executing __init__.py, which can crash
    when transitive deps like pkg_resources are missing (e.g. SAM3 on Py3.12+).
    """
    try:
        distribution(dist_name)
        return True
    except PackageNotFoundError:
        return False


def main():
    print("[FFMPEGA] Installing optional dependencies...")

    # --- SAM3 (object segmentation for auto_mask) ---
    if not is_installed("sam3"):
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

    # --- LaMa inpainting (object removal for auto_mask) ---
    if not is_installed("simple-lama-inpainting"):
        print("[FFMPEGA] Installing simple-lama-inpainting (--no-deps to avoid torch/numpy conflicts)...")
        result = subprocess.run(
            [*pip, "--no-deps", "simple-lama-inpainting"],
        )
        if result.returncode == 0:
            print("[FFMPEGA] ✓ simple-lama-inpainting installed successfully")
        else:
            print("[FFMPEGA] ✗ simple-lama-inpainting installation failed — LaMa inpainting will use black fill fallback")
    else:
        print("[FFMPEGA] ✓ simple-lama-inpainting already installed")

    # --- MMAudio (AI audio synthesis for generate_audio) ---
    if not is_installed("mmaudio"):
        print("[FFMPEGA] Installing MMAudio (--no-deps to avoid torch/numpy conflicts)...")
        result = subprocess.run(
            [*pip, "--no-deps", "git+https://github.com/hkchengrex/MMAudio.git"],
        )
        if result.returncode == 0:
            print("[FFMPEGA] ✓ MMAudio installed successfully")
        else:
            print("[FFMPEGA] ✗ MMAudio installation failed — generate_audio skill will be unavailable")
    else:
        print("[FFMPEGA] ✓ MMAudio already installed")

    # --- MMAudio companion deps (safe to install normally) ---
    mmaudio_companion = [
        "torchdiffeq", "open-clip-torch", "scipy", "colorlog",
        "omegaconf", "librosa", "einops",
    ]
    missing = [pkg for pkg in mmaudio_companion if not is_installed(pkg)]
    if missing:
        print(f"[FFMPEGA] Installing MMAudio companion deps: {', '.join(missing)}...")
        result = subprocess.run([*pip, *missing])
        if result.returncode == 0:
            print("[FFMPEGA] ✓ MMAudio companion deps installed successfully")
        else:
            print("[FFMPEGA] ✗ Some MMAudio companion deps failed — generate_audio may not work")
    else:
        print("[FFMPEGA] ✓ MMAudio companion deps already installed")

    # --- AudioX (music generation, audio inpainting) ---
    # AudioX is a fork of stable-audio-tools with custom model architecture.
    # We MUST install from the AudioX GitHub repo, NOT the vanilla PyPI
    # stable-audio-tools (which lacks video_fps and other AudioX modifications).
    # Install with --no-deps to avoid pulling training-only dependencies.
    if not is_installed("audiox"):
        print("[FFMPEGA] Installing AudioX from GitHub (--no-deps)...")
        result = subprocess.run(
            [*pip, "--no-deps", "git+https://github.com/ZeyueT/AudioX.git"],
        )
        if result.returncode == 0:
            print("[FFMPEGA] ✓ AudioX installed successfully")
        else:
            print("[FFMPEGA] ✗ AudioX installation failed — generate_music will be unavailable")
    else:
        print("[FFMPEGA] ✓ AudioX already installed")

    # AudioX companion deps (safe to install normally)
    # Note: k-diffusion → clip → pkg_resources requires setuptools<81
    # (setuptools 82+ removed pkg_resources)
    audiox_companion = [
        "alias-free-torch", "x-transformers", "einops-exts", "k-diffusion",
        "descript-audio-codec", "descript-audiotools",
        "vector-quantize-pytorch", "local-attention", "ema-pytorch",
        "aeiou", "encodec", "auraloss", "laion-clap",
        "setuptools<81",  # k-diffusion → clip → pkg_resources
    ]
    missing_ax = [pkg for pkg in audiox_companion if not is_installed(pkg)]
    if missing_ax:
        print(f"[FFMPEGA] Installing AudioX companion deps: {', '.join(missing_ax)}...")
        result = subprocess.run([*pip, *missing_ax])
        if result.returncode == 0:
            print("[FFMPEGA] ✓ AudioX companion deps installed successfully")
        else:
            print("[FFMPEGA] ✗ Some AudioX companion deps failed — generate_music may not work")
    else:
        print("[FFMPEGA] ✓ AudioX companion deps already installed")

    # --- SAM-Audio (audio separation / sound isolation) ---
    # SAM-Audio from Meta — Segment Anything Model for Audio.
    # Install with --no-deps to avoid pulling imagebind, laion-clap,
    # audiobox_aesthetics, torchcodec (not needed for core separation).
    if not is_installed("sam_audio"):
        print("[FFMPEGA] Installing SAM-Audio from GitHub (--no-deps)...")
        result = subprocess.run(
            [*pip, "--no-deps", "git+https://github.com/facebookresearch/sam-audio.git"],
        )
        if result.returncode == 0:
            print("[FFMPEGA] ✓ SAM-Audio installed successfully")
        else:
            print("[FFMPEGA] ✗ SAM-Audio installation failed — audio_separate will be unavailable")
    else:
        print("[FFMPEGA] ✓ SAM-Audio already installed")

    # SAM-Audio companion deps
    # xformers + torchcodec are hidden transitive deps from perception_models
    sam_audio_companion = [
        "torchdiffeq", "pydub", "xformers", "torchcodec",
    ]
    # These are git-only packages — check and install separately
    sam_audio_git_deps = {
        "dacvae": "git+https://github.com/facebookresearch/dacvae.git",
        "perception_models": "git+https://github.com/facebookresearch/perception_models@unpin-deps",
    }
    for pkg_name, git_url in sam_audio_git_deps.items():
        if not is_installed(pkg_name):
            print(f"[FFMPEGA] Installing SAM-Audio dep: {pkg_name}...")
            result = subprocess.run([*pip, "--no-deps", git_url])
            if result.returncode == 0:
                print(f"[FFMPEGA] ✓ {pkg_name} installed")
            else:
                print(f"[FFMPEGA] ✗ {pkg_name} install failed")
        else:
            print(f"[FFMPEGA] ✓ {pkg_name} already installed")

    # Regular pip deps for SAM-Audio
    missing_sa = [pkg for pkg in sam_audio_companion if not is_installed(pkg)]
    if missing_sa:
        print(f"[FFMPEGA] Installing SAM-Audio companion deps: {', '.join(missing_sa)}...")
        result = subprocess.run([*pip, *missing_sa])
        if result.returncode == 0:
            print("[FFMPEGA] ✓ SAM-Audio companion deps installed successfully")
        else:
            print("[FFMPEGA] ✗ Some SAM-Audio companion deps failed — audio_separate may not work")
    else:
        print("[FFMPEGA] ✓ SAM-Audio companion deps already installed")

    print("[FFMPEGA] Dependency installation complete")


if __name__ == "__main__":
    main()
else:
    # ComfyUI Manager imports this file — run main() on import
    main()
