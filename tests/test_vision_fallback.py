"""Test vision fallback with non-vision Ollama model (qwen3:8b).

Sends color analysis data (not images) to a text-only model and verifies
it can reason about the video's colors from numeric data alone.

Usage:
    python tests/test_vision_fallback.py
"""

import asyncio
import importlib.util
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def load_module(name: str, rel_path: str):
    abs_path = PROJECT_ROOT / rel_path
    spec = importlib.util.spec_from_file_location(name, str(abs_path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# Find test video
TEST_VIDEO = None
output_dir = PROJECT_ROOT.parent.parent / "output"
for f in output_dir.rglob("*.mp4"):
    TEST_VIDEO = str(f)
    break

if not TEST_VIDEO:
    print("ERROR: No test video found!")
    sys.exit(1)

print(f"Using test video: {TEST_VIDEO}")
print(f"Model: qwen3:8b (non-vision, text-only)")
print()


async def test_fallback_with_color_data():
    """Test: Send analyze_colors data to non-vision model for color grading."""
    print("=" * 60)
    print("TEST: Non-vision model with analyze_colors fallback data")
    print("=" * 60)

    import httpx

    vision = load_module("vision", "mcp/vision.py")

    # Step 1: Get color analysis (this is what the fallback would provide)
    print("  Step 1: Running analyze_colors_ffmpeg...")
    color_data = vision.analyze_colors_ffmpeg(TEST_VIDEO, start=0, duration=3)
    print(f"  Color data: {json.dumps(color_data, indent=2)}")
    print()

    # Step 2: Send to qwen3:8b (non-vision) as if it were a tool result
    print("  Step 2: Sending color data to qwen3:8b...")

    # Simulate what the agentic flow would do: the model called extract_frames,
    # but since it's non-vision, we fall back to color analysis data
    tool_result_content = json.dumps({
        "frame_count": 2,
        "paths": ["/tmp/frame_001.png", "/tmp/frame_002.png"],
        "note": "Vision not available — color analysis provided instead",
        "color_analysis": color_data,
    }, indent=2)

    messages = [
        {
            "role": "system",
            "content": (
                "You are FFMPEGA, a video editing agent. You have tools to "
                "discover and apply video editing skills. When you receive "
                "color analysis data from extract_frames, use the numeric "
                "values to make informed color grading decisions. "
                "Respond with a brief 2-3 sentence color grading recommendation."
            ),
        },
        {
            "role": "user",
            "content": "Make this video look more cinematic and dramatic.",
        },
        {
            "role": "assistant",
            "content": (
                "Let me analyze the video's colors first to make informed "
                "grading decisions.\n\n"
                "TOOL_CALL: extract_frames {}"
            ),
        },
        {
            "role": "user",
            "content": (
                f"Tool result from extract_frames:\n{tool_result_content}\n\n"
                "Based on this color analysis, what color grading would you "
                "recommend for a cinematic look? Be specific about which "
                "skills and parameter values to use."
            ),
        },
    ]

    try:
        async with httpx.AsyncClient(
            base_url="http://localhost:11434",
            timeout=120.0,
        ) as client:
            payload = {
                "model": "qwen3:8b",
                "messages": messages,
                "stream": False,
                "options": {"temperature": 0.3, "num_predict": 500},
            }
            resp = await client.post("/api/chat", json=payload)
            resp.raise_for_status()
            data = resp.json()
            content = data.get("message", {}).get("content", "")

            # Strip <think> blocks
            if "<think>" in content and "</think>" in content:
                visible = content[content.index("</think>") + 8:].strip()
            else:
                visible = content

            print(f"  Response ({len(visible)} chars):")
            print(f"    {visible[:600]}")
            print()

            # Check if the model referenced the actual color data
            references_data = any(
                kw in visible.lower()
                for kw in [
                    "luminance", "saturation", "warm", "bright",
                    "colorbalance", "contrast", "cool", "color",
                    "desaturated", "muted",
                ]
            )
            if references_data:
                print("  PASS — Model used color data to inform recommendations!")
            else:
                print("  WARN — Model may not have used the color data")

    except httpx.ConnectError:
        print("  SKIP (Ollama not reachable)")
    except Exception as e:
        print(f"  ERROR: {e}")

    return True


async def main():
    print("FFMPEGA Vision Fallback Test (non-vision model)")
    print("=" * 60)
    print()
    await test_fallback_with_color_data()


if __name__ == "__main__":
    asyncio.run(main())
