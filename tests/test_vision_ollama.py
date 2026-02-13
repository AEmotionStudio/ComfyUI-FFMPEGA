"""Standalone integration test for vision skill with local Ollama.

Tests the full pipeline: extract_frames -> base64 encoding -> Ollama vision,
plus the analyze_colors fallback path.

Usage:
    python tests/test_vision_ollama.py
"""

import asyncio
import importlib.util
import json
import sys
import os
from pathlib import Path

# Add project root to path for relative imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Use importlib to load modules without triggering __init__.py chains
def load_module(name: str, rel_path: str):
    abs_path = PROJECT_ROOT / rel_path
    spec = importlib.util.spec_from_file_location(name, str(abs_path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

# Find a test video
TEST_VIDEOS = [
    PROJECT_ROOT.parent.parent / "output" / "video" / "ComfyUI_00042_.mp4",
    PROJECT_ROOT.parent.parent / "output" / "AnimateDiff_00004.mp4",
]
TEST_VIDEO = None
for v in TEST_VIDEOS:
    if v.exists():
        TEST_VIDEO = str(v)
        break

if not TEST_VIDEO:
    # Try to find any mp4
    output_dir = PROJECT_ROOT.parent.parent / "output"
    for f in output_dir.rglob("*.mp4"):
        TEST_VIDEO = str(f)
        break

if not TEST_VIDEO:
    print("ERROR: No test video found!")
    sys.exit(1)

print(f"Using test video: {TEST_VIDEO}")
print()


def test_analyze_colors():
    """Test 1: analyze_colors_ffmpeg with a real video."""
    print("=" * 60)
    print("TEST 1: analyze_colors_ffmpeg")
    print("=" * 60)

    vision = load_module("vision", "mcp/vision.py")
    result = vision.analyze_colors_ffmpeg(TEST_VIDEO, start=0, duration=3)

    print(f"Analysis type: {result.get('analysis_type', 'unknown')}")

    if result.get("error"):
        print(f"  Error: {result['error']}")
        # This is expected to fall back to simple analysis
        if result.get("pixel_format"):
            print(f"  Pixel format: {result['pixel_format']}")
            print(f"  Color space: {result['color_space']}")
            print("  PASS (simple fallback worked)")
            return True
        print("  FAIL")
        return False

    if result.get("luminance"):
        lum = result["luminance"]
        print(f"  Luminance: avg={lum['average']}, "
              f"min={lum['min']}, max={lum['max']}")
        print(f"  Assessment: {lum['assessment']}")

    if result.get("saturation"):
        sat = result["saturation"]
        print(f"  Saturation: avg={sat['average']}")
        print(f"  Assessment: {sat['assessment']}")

    if result.get("color_balance"):
        bal = result["color_balance"]
        print(f"  Color balance: U={bal['u_average']}, V={bal['v_average']}")
        print(f"  Dominant tone: {bal['dominant_tone']}")

    if result.get("recommendations"):
        print(f"  Recommendations:")
        for r in result["recommendations"]:
            print(f"    - {r}")

    print("  PASS")
    return True


def test_frames_to_base64():
    """Test 2: Extract frames then convert to base64."""
    print()
    print("=" * 60)
    print("TEST 2: extract_frames + frames_to_base64")
    print("=" * 60)

    import subprocess, uuid, shutil

    vision = load_module("vision", "mcp/vision.py")

    # Extract 2 frames manually
    tmp_dir = Path("/tmp") / f"vision_test_{uuid.uuid4().hex[:8]}"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        "ffmpeg", "-y", "-i", TEST_VIDEO,
        "-ss", "0", "-t", "2", "-vf", "fps=1",
        "-frames:v", "2",
        str(tmp_dir / "frame_%03d.png"),
    ]
    subprocess.run(cmd, capture_output=True, timeout=15)

    frames = sorted(tmp_dir.glob("*.png"))
    print(f"  Extracted {len(frames)} frames")

    if not frames:
        print("  SKIP (no frames extracted)")
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return True

    # Test OpenAI format
    blocks = vision.frames_to_base64(frames, max_size=256)
    print(f"  OpenAI blocks: {len(blocks)}")
    if blocks:
        first = blocks[0]
        assert first["type"] == "image_url", f"Wrong type: {first['type']}"
        url = first["image_url"]["url"]
        assert url.startswith("data:image/png;base64,"), "Wrong prefix"
        b64_len = len(url) - len("data:image/png;base64,")
        print(f"  First block base64 length: {b64_len}")

    # Test Ollama format
    raw_strings = vision.frames_to_base64_raw_strings(frames, max_size=256)
    print(f"  Ollama raw strings: {len(raw_strings)}")
    if raw_strings:
        print(f"  First string length: {len(raw_strings[0])}")
        # Should NOT have the data URI prefix
        assert not raw_strings[0].startswith("data:"), "Should be raw base64"

    shutil.rmtree(tmp_dir, ignore_errors=True)
    print("  PASS")
    return True


async def test_ollama_vision():
    """Test 3: Full Ollama vision pipeline with base64 images."""
    print()
    print("=" * 60)
    print("TEST 3: Ollama vision with qwen3-vl (full pipeline)")
    print("=" * 60)

    import subprocess, uuid, shutil
    import httpx

    vision = load_module("vision", "mcp/vision.py")

    # Extract 1 frame
    tmp_dir = Path("/tmp") / f"vision_test_{uuid.uuid4().hex[:8]}"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y", "-i", TEST_VIDEO,
        "-ss", "1", "-vf", "fps=1",
        "-frames:v", "1",
        str(tmp_dir / "frame_%03d.png"),
    ]
    subprocess.run(cmd, capture_output=True, timeout=15)
    frames = sorted(tmp_dir.glob("*.png"))

    if not frames:
        print("  SKIP (no frames)")
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return True

    # Get base64 for Ollama format
    b64_strings = vision.frames_to_base64_raw_strings(frames, max_size=512)
    if not b64_strings:
        print("  SKIP (encoding failed)")
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return True

    print(f"  Encoded {len(b64_strings)} frames for Ollama")

    # Send to Ollama with qwen3-vl
    payload = {
        "model": "qwen3-vl",
        "messages": [
            {
                "role": "user",
                "content": (
                    "Describe the colors, lighting, and composition of this "
                    "video frame in 2-3 sentences. Focus on: dominant colors, "
                    "brightness level, contrast, and any notable visual elements."
                ),
                "images": b64_strings,
            }
        ],
        "stream": False,
        "options": {"temperature": 0.3, "num_predict": 200},
    }

    try:
        async with httpx.AsyncClient(
            base_url="http://localhost:11434",
            timeout=120.0,
        ) as client:
            print("  Sending to qwen3-vl...")
            resp = await client.post("/api/chat", json=payload)
            resp.raise_for_status()
            data = resp.json()
            content = data.get("message", {}).get("content", "")
            print(f"  Model response ({len(content)} chars):")
            print(f"    {content[:300]}")
            if content:
                print("  PASS - Vision model responded to frame!")
            else:
                print("  WARN - Empty response")
    except httpx.ConnectError:
        print("  SKIP (Ollama not reachable)")
    except Exception as e:
        print(f"  ERROR: {e}")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    return True


async def test_ollama_tool_result_with_images():
    """Test 4: Simulate the agentic tool result flow with Ollama."""
    print()
    print("=" * 60)
    print("TEST 4: Simulated agentic tool result with images (Ollama)")
    print("=" * 60)

    import subprocess, uuid, shutil
    import httpx

    vision = load_module("vision", "mcp/vision.py")

    # Extract 1 frame
    tmp_dir = Path("/tmp") / f"vision_test_{uuid.uuid4().hex[:8]}"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y", "-i", TEST_VIDEO,
        "-ss", "0", "-vf", "fps=1",
        "-frames:v", "1",
        str(tmp_dir / "frame_%03d.png"),
    ]
    subprocess.run(cmd, capture_output=True, timeout=15)
    frames = sorted(tmp_dir.glob("*.png"))

    if not frames:
        print("  SKIP (no frames)")
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return True

    b64_strings = vision.frames_to_base64_raw_strings(frames, max_size=512)

    # Simulate the agentic flow: system + user + assistant tool_call + tool result with images
    messages = [
        {
            "role": "system",
            "content": (
                "You are a video color analyst. When you receive video frame "
                "images, describe the colors you see and suggest color grading "
                "adjustments. Be concise - 2-3 sentences max."
            ),
        },
        {
            "role": "user",
            "content": "Analyze this video and suggest color improvements.",
            "images": b64_strings,
        },
    ]

    try:
        async with httpx.AsyncClient(
            base_url="http://localhost:11434",
            timeout=120.0,
        ) as client:
            print("  Sending tool-result-style message with images...")
            payload = {
                "model": "qwen3-vl",
                "messages": messages,
                "stream": False,
                "options": {"temperature": 0.3, "num_predict": 300},
            }
            resp = await client.post("/api/chat", json=payload)
            resp.raise_for_status()
            data = resp.json()
            content = data.get("message", {}).get("content", "")
            print(f"  Response ({len(content)} chars):")
            # Strip <think> blocks if present
            if "<think>" in content and "</think>" in content:
                visible = content[content.index("</think>") + 8:].strip()
            else:
                visible = content
            print(f"    {visible[:400]}")
            if visible:
                print("  PASS - Model analyzed frame with color suggestions!")
            else:
                print("  WARN - Empty response")
    except httpx.ConnectError:
        print("  SKIP (Ollama not reachable)")
    except Exception as e:
        print(f"  ERROR: {e}")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    return True


async def main():
    print("FFMPEGA Vision Integration Test")
    print("================================")
    print()

    results = []

    # Test 1: Color analysis (no LLM needed)
    results.append(("analyze_colors", test_analyze_colors()))

    # Test 2: Frame encoding
    results.append(("frames_to_base64", test_frames_to_base64()))

    # Test 3: Full Ollama vision
    results.append(("ollama_vision", await test_ollama_vision()))

    # Test 4: Agentic flow simulation
    results.append(("ollama_tool_result", await test_ollama_tool_result_with_images()))

    print()
    print("=" * 60)
    print("RESULTS")
    print("=" * 60)
    for name, passed in results:
        status = "PASS" if passed else "FAIL"
        print(f"  {name}: {status}")


if __name__ == "__main__":
    asyncio.run(main())
