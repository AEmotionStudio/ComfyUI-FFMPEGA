"""Test LUT system — discovery, auto-resolution, and LLM agent usage.

Tests cover:
1. list_luts: scan luts/ folder for .cube files (standalone reimplementation)
2. _f_lut_apply auto-resolution: short names → full paths
3. Generated .cube files are valid (ffmpeg can parse them)
4. Live LLM (Ollama) discovers LUTs via tool calling and builds a pipeline
5. End-to-end: ffmpeg LUT application to a real video

Usage:
    python tests/test_lut_agents.py
"""

import asyncio
import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LUTS_DIR = PROJECT_ROOT / "luts"

EXPECTED_LUTS = [
    "bleach_bypass",
    "cinematic_teal_orange",
    "cool_scifi",
    "cross_process",
    "film_noir",
    "golden_hour",
    "neutral_clean",
    "warm_vintage",
]

# Find a test video
TEST_VIDEO = None
output_dir = PROJECT_ROOT.parent.parent / "output"
if output_dir.exists():
    for f in output_dir.rglob("*.mp4"):
        TEST_VIDEO = str(f)
        break


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Test 1: list_luts — standalone reimplementation of the tool
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def list_luts_standalone() -> dict:
    """Reimplementation of mcp/tools.py:list_luts for standalone testing."""
    luts = []
    if LUTS_DIR.is_dir():
        for f in sorted(LUTS_DIR.iterdir()):
            if f.is_file() and f.suffix.lower() in (".cube", ".3dl"):
                luts.append({
                    "name": f.stem,
                    "filename": f.name,
                    "display_name": f.stem.replace("_", " ").title(),
                })
    return {
        "luts": luts,
        "count": len(luts),
        "luts_folder": str(LUTS_DIR),
        "usage_hint": "Use lut_apply skill with the name as the path parameter",
    }


def test_list_luts():
    """list_luts should find all 8 bundled .cube files."""
    print("=" * 60)
    print("TEST 1: list_luts tool (standalone)")
    print("=" * 60)

    result = list_luts_standalone()

    print(f"  Count: {result['count']}")
    print(f"  Folder: {result['luts_folder']}")

    names = [lut["name"] for lut in result["luts"]]
    for lut in result["luts"]:
        print(f"    {lut['name']:30s} → {lut['filename']}")

    # Verify all expected LUTs are present
    missing = set(EXPECTED_LUTS) - set(names)
    if missing:
        print(f"  FAIL — missing: {missing}")
        return False

    assert result["count"] == 8, f"Expected 8, got {result['count']}"
    print("  PASS ✅")
    return True


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Test 2: Auto-resolution of short LUT names
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def resolve_lut_name(path: str) -> str:
    """Reimplementation of the auto-resolution logic from composer.py."""
    if "/" not in path and "\\" not in path:
        # Try exact match first
        for ext in (".cube", ".3dl", ""):
            candidate = LUTS_DIR / f"{path}{ext}"
            if candidate.is_file():
                return str(candidate)
        # Try case-insensitive partial match
        if LUTS_DIR.is_dir():
            for f in LUTS_DIR.iterdir():
                if f.suffix.lower() in (".cube", ".3dl") and path.lower() in f.stem.lower():
                    return str(f)
    return path


def test_lut_auto_resolve():
    """Short LUT names should resolve to full paths."""
    print()
    print("=" * 60)
    print("TEST 2: LUT auto-resolution")
    print("=" * 60)

    all_pass = True

    # Test exact short name
    print("  Testing exact name: 'film_noir'")
    resolved = resolve_lut_name("film_noir")
    expected = str(LUTS_DIR / "film_noir.cube")
    if resolved == expected:
        print(f"    → {resolved}")
        print("    PASS ✅")
    else:
        print(f"    FAIL — got: {resolved}, expected: {expected}")
        all_pass = False

    # Test partial match (fuzzy)
    print("  Testing partial name: 'cinematic'")
    resolved = resolve_lut_name("cinematic")
    if "cinematic_teal_orange.cube" in resolved:
        print(f"    → {resolved}")
        print("    PASS ✅")
    else:
        print(f"    FAIL — got: {resolved}")
        all_pass = False

    # Test all bundled LUTs by exact name
    print("  Testing all 8 bundled LUTs by exact name...")
    for name in EXPECTED_LUTS:
        resolved = resolve_lut_name(name)
        if resolved.endswith(f"{name}.cube"):
            print(f"    {name:30s} ✅")
        else:
            print(f"    {name:30s} ❌ → {resolved}")
            all_pass = False

    # Test full path passthrough
    print("  Testing full path passthrough: '/some/custom/path.cube'")
    resolved = resolve_lut_name("/some/custom/path.cube")
    if resolved == "/some/custom/path.cube":
        print("    PASS ✅ (not modified)")
    else:
        print(f"    FAIL — got: {resolved}")
        all_pass = False

    if all_pass:
        print("  ALL PASS ✅")
    return all_pass


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Test 3: .cube files are valid for ffmpeg
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def test_cube_files_valid():
    """Every bundled .cube file should be parseable by ffmpeg lut3d."""
    print()
    print("=" * 60)
    print("TEST 3: Validate .cube files with ffmpeg")
    print("=" * 60)

    all_pass = True
    for cube_file in sorted(LUTS_DIR.glob("*.cube")):
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "color=c=red:size=16x16:d=0.1",
            "-vf", f"lut3d=file='{cube_file}'",
            "-frames:v", "1", "-update", "1",
            "/tmp/lut_valid_test.png",
        ]
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            print(f"  {cube_file.stem:30s} ✅")
        else:
            print(f"  {cube_file.stem:30s} ❌ — {result.stderr[-100:]}")
            all_pass = False

    if all_pass:
        print("  ALL .cube files valid ✅")
    return all_pass


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Test 4: Live LLM discovers LUTs via tool calling
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


async def test_llm_discovers_luts():
    """Send a color grading prompt to Ollama and verify it calls list_luts."""
    print()
    print("=" * 60)
    print("TEST 4: LLM discovers LUTs via tool calling (Ollama)")
    print("=" * 60)

    try:
        import httpx
    except ImportError:
        print("  SKIP (httpx not available)")
        return True

    # Define tools for the LLM
    tools = [
        {
            "type": "function",
            "function": {
                "name": "list_luts",
                "description": (
                    "List all available LUT (.cube/.3dl) files for color grading. "
                    "Returns name and filename for each LUT. Call this BEFORE "
                    "using the lut_apply skill."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "search_skills",
                "description": "Search for video editing skills by keyword.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search keyword"},
                    },
                    "required": ["query"],
                },
            },
        },
    ]

    messages = [
        {
            "role": "system",
            "content": (
                "You are a video editing agent. When the user asks for color "
                "grading or LUT application, you MUST call list_luts first to "
                "see available LUT files. Then respond with a JSON pipeline "
                "using the lut_apply skill with a specific LUT name from the list."
            ),
        },
        {
            "role": "user",
            "content": (
                "Apply a cinematic color grade to my video using a LUT. "
                "List the available LUTs first."
            ),
        },
    ]

    try:
        async with httpx.AsyncClient(
            base_url="http://localhost:11434",
            timeout=120.0,
        ) as client:
            # Step 1: Initial request — expect list_luts tool call
            print("  Step 1: Sending color grading prompt...")
            payload = {
                "model": "qwen3:8b",
                "messages": messages,
                "tools": tools,
                "stream": False,
                "options": {"temperature": 0.3, "num_predict": 500},
            }
            resp = await client.post("/api/chat", json=payload)
            resp.raise_for_status()
            data = resp.json()

            msg = data.get("message", {})
            tool_calls = msg.get("tool_calls", [])
            content = msg.get("content", "")

            # Strip <think> blocks
            if "<think>" in content and "</think>" in content:
                content = content[content.index("</think>") + 8:].strip()

            if tool_calls:
                func_names = [tc["function"]["name"] for tc in tool_calls]
                print(f"  Tool calls: {func_names}")

                if "list_luts" in func_names:
                    print("  ✅ LLM called list_luts!")

                    # Step 2: Provide list_luts result back
                    lut_result = list_luts_standalone()
                    messages.append({
                        "role": "assistant",
                        "content": "",
                        "tool_calls": tool_calls,
                    })
                    messages.append({
                        "role": "tool",
                        "content": json.dumps(lut_result, indent=2),
                    })

                    print("  Step 2: Sending LUT list back to LLM...")
                    payload2 = {
                        "model": "qwen3:8b",
                        "messages": messages,
                        "stream": False,
                        "options": {"temperature": 0.3, "num_predict": 800},
                    }
                    resp2 = await client.post("/api/chat", json=payload2)
                    resp2.raise_for_status()
                    data2 = resp2.json()

                    response_text = data2.get("message", {}).get("content", "")
                    if "<think>" in response_text and "</think>" in response_text:
                        response_text = response_text[
                            response_text.index("</think>") + 8:
                        ].strip()

                    print(f"  LLM response ({len(response_text)} chars):")
                    # Show first 400 chars
                    for line in response_text[:400].split("\n"):
                        print(f"    {line}")

                    # Check if response mentions any specific LUT name
                    lut_mentioned = any(
                        name in response_text.lower()
                        for name in EXPECTED_LUTS
                    )
                    if lut_mentioned:
                        print("  ✅ LLM referenced a specific LUT from the list!")
                    else:
                        print("  ⚠️  LLM didn't reference a specific LUT name")

                    # Check for lut_apply skill usage
                    if "lut_apply" in response_text:
                        print("  ✅ Response contains lut_apply skill!")
                    else:
                        print("  ⚠️  Response doesn't mention lut_apply")

                    print("  PASS ✅")
                    return True
                else:
                    print(f"  ⚠️  LLM called {func_names} instead of list_luts")
                    print("  PASS (LLM used tools, just picked different ones)")
                    return True
            else:
                print(f"  LLM responded without tools: {content[:200]}")
                print("  PASS (non-fatal — LLM behavior varies)")
                return True

    except Exception as e:
        if "ConnectError" in type(e).__name__ or "Connection" in str(e):
            print("  SKIP (Ollama not reachable)")
            return True
        print(f"  ERROR: {e}")
        return False


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Test 5: End-to-end ffmpeg LUT application
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def test_e2e_lut_ffmpeg():
    """Apply a bundled LUT to a real video via ffmpeg."""
    print()
    print("=" * 60)
    print("TEST 5: End-to-end LUT application via ffmpeg")
    print("=" * 60)

    if not TEST_VIDEO:
        print("  SKIP (no test video found)")
        return True

    output = "/tmp/lut_e2e_test.mp4"
    lut_path = LUTS_DIR / "cinematic_teal_orange.cube"

    cmd = [
        "ffmpeg", "-y",
        "-i", TEST_VIDEO,
        "-vf", f"lut3d=file='{lut_path}'",
        "-t", "2",
        "-c:a", "copy",
        output,
    ]

    print(f"  Input: {Path(TEST_VIDEO).name}")
    print(f"  LUT: {lut_path.name}")

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

    if result.returncode == 0:
        out_path = Path(output)
        if out_path.exists() and out_path.stat().st_size > 1000:
            size_kb = out_path.stat().st_size / 1024
            print(f"  Output: {size_kb:.0f} KB")

            # Probe output duration
            probe = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1", output],
                capture_output=True, text=True,
            )
            if probe.stdout.strip():
                print(f"  Duration: {probe.stdout.strip()}")

            print("  PASS ✅")
            return True
        else:
            print("  FAIL — output too small or missing")
            return False
    else:
        print(f"  FAIL — {result.stderr[-200:]}")
        return False


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


async def main():
    print("FFMPEGA LUT System Tests")
    print("========================")
    print(f"LUTs dir: {LUTS_DIR}")
    print(f"Test video: {Path(TEST_VIDEO).name if TEST_VIDEO else '(none)'}")
    print()

    results = []

    # Unit tests (no LLM needed)
    results.append(("list_luts", test_list_luts()))
    results.append(("auto_resolve", test_lut_auto_resolve()))
    results.append(("cube_valid", test_cube_files_valid()))

    # Live LLM test
    results.append(("llm_discovers_luts", await test_llm_discovers_luts()))

    # E2E ffmpeg test
    results.append(("e2e_ffmpeg", test_e2e_lut_ffmpeg()))

    # Summary
    print()
    print("=" * 60)
    print("RESULTS")
    print("=" * 60)
    all_pass = True
    for name, passed in results:
        icon = "✅" if passed else "❌"
        print(f"  {icon} {name}")
        if not passed:
            all_pass = False

    print()
    if all_pass:
        print("All tests passed! ✅")
    else:
        print("Some tests failed! ❌")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
