"""Tests for PTCExecutor: sandbox security, tool access, and output capture.

Tests cover:
- Sandbox security (blocked builtins: import, open, eval, exec)
- Tool function access within sandbox
- Output capture via print()
- Timeout enforcement
- Error handling (syntax errors, runtime errors)
- JSON serialization in sandbox
- End-to-end orchestration (search → details → pipeline)
"""

import json
import pytest

try:
    from core.ptc_executor import PTCExecutor, PTCResult
except (ImportError, ModuleNotFoundError):
    import importlib.util
    import os
    _spec = importlib.util.spec_from_file_location(
        "core.ptc_executor",
        os.path.join(os.path.dirname(__file__), "..", "core", "ptc_executor.py"),
    )
    _mod = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)
    PTCExecutor = _mod.PTCExecutor
    PTCResult = _mod.PTCResult


# ── Fixtures ─────────────────────────────────────────────────────── #

def _mock_search_skills(query: str) -> dict:
    """Mock search_skills that always returns a cinematic skill."""
    return {
        "query": query,
        "match_count": 2,
        "matches": [
            {"name": "cinematic_grade", "category": "visual", "description": "Cinematic color grading", "tags": []},
            {"name": "film_grain", "category": "visual", "description": "Film grain overlay", "tags": []},
        ],
    }


def _mock_get_skill_details(skill_name: str) -> dict:
    """Mock get_skill_details with parameter info."""
    return {
        "name": skill_name,
        "description": f"Details for {skill_name}",
        "params": {
            "intensity": {"type": "string", "default": "medium", "choices": ["low", "medium", "high"]},
        },
    }


def _mock_list_skills(category=None) -> dict:
    """Mock list_skills."""
    return {
        "total_count": 2,
        "skills": [
            {"name": "blur", "category": "visual", "description": "Blur filter", "parameters": [], "tags": [], "examples": []},
            {"name": "speed", "category": "temporal", "description": "Speed control", "parameters": [], "tags": [], "examples": []},
        ],
        "by_category": {},
    }


def _mock_build_pipeline(skills, input_path="/tmp/in.mp4", output_path="/tmp/out.mp4") -> dict:
    """Mock build_pipeline returning a command string."""
    return {
        "success": True,
        "command": f"ffmpeg -i {input_path} -vf 'test' {output_path}",
        "command_args": ["ffmpeg", "-i", input_path, "-vf", "test", output_path],
        "explanation": "Test pipeline",
        "step_count": len(skills),
        "errors": [],
    }


def _mock_analyze_video(video_path: str) -> dict:
    return {"width": 1920, "height": 1080, "duration": 10.0, "fps": 24}


def _mock_list_luts() -> dict:
    return {"luts": [{"name": "teal_orange", "path": "/luts/teal_orange.cube"}]}


@pytest.fixture
def executor():
    """Create a PTCExecutor with mock tool handlers."""
    return PTCExecutor(
        tool_handlers={
            "search_skills": _mock_search_skills,
            "get_skill_details": _mock_get_skill_details,
            "list_skills": _mock_list_skills,
            "build_pipeline": _mock_build_pipeline,
            "analyze_video": _mock_analyze_video,
            "list_luts": _mock_list_luts,
        },
        timeout=5.0,
    )


# ── Sandbox security tests ──────────────────────────────────────── #

class TestSandboxSecurity:
    """Verify that dangerous operations are blocked."""

    def test_import_blocked(self, executor):
        """import statements should raise NameError."""
        result = executor.execute("import os")
        assert not result.success
        assert "import" in result.error.lower() or "name" in result.error.lower()

    def test_import_function_blocked(self, executor):
        """__import__ should not be available."""
        result = executor.execute("__import__('os')")
        assert not result.success

    def test_open_blocked(self, executor):
        """open() should not be available."""
        result = executor.execute("open('/etc/passwd')")
        assert not result.success

    def test_eval_blocked(self, executor):
        """eval() should not be available."""
        result = executor.execute("eval('1+1')")
        assert not result.success

    def test_exec_blocked(self, executor):
        """exec() should not be accessible inside sandbox code."""
        result = executor.execute("exec('print(1)')")
        assert not result.success

    def test_globals_access_blocked(self, executor):
        """Attempting to access globals() or manipulate builtins."""
        result = executor.execute("globals()['__builtins__']['__import__']('os')")
        assert not result.success

    def test_subprocess_blocked(self, executor):
        """Can't import subprocess."""
        result = executor.execute("import subprocess; subprocess.run(['ls'])")
        assert not result.success


# ── Tool access tests ────────────────────────────────────────────── #

class TestToolAccess:
    """Verify tool functions are callable from sandbox."""

    def test_search_skills_callable(self, executor):
        """search_skills should be callable and return results."""
        result = executor.execute(
            'result = search_skills("cinematic")\n'
            'print(json.dumps(result))'
        )
        assert result.success
        data = json.loads(result.stdout.strip())
        assert data["match_count"] == 2
        assert data["matches"][0]["name"] == "cinematic_grade"

    def test_get_skill_details_callable(self, executor):
        """get_skill_details should be callable."""
        result = executor.execute(
            'details = get_skill_details("blur")\n'
            'print(details["name"])'
        )
        assert result.success
        assert result.stdout.strip() == "blur"

    def test_list_skills_callable(self, executor):
        """list_skills should be callable with default args."""
        result = executor.execute(
            'skills = list_skills()\n'
            'print(skills["total_count"])'
        )
        assert result.success
        assert result.stdout.strip() == "2"

    def test_build_pipeline_callable(self, executor):
        """build_pipeline should be callable with multiple args."""
        result = executor.execute(
            'pipeline = build_pipeline(\n'
            '    [{"name": "blur", "params": {"radius": 5}}],\n'
            '    "/tmp/in.mp4",\n'
            '    "/tmp/out.mp4"\n'
            ')\n'
            'print(pipeline["success"])'
        )
        assert result.success
        assert result.stdout.strip() == "True"

    def test_list_luts_no_args(self, executor):
        """list_luts with no args should work."""
        result = executor.execute(
            'luts = list_luts()\n'
            'print(len(luts["luts"]))'
        )
        assert result.success
        assert result.stdout.strip() == "1"


# ── Output capture tests ─────────────────────────────────────────── #

class TestOutputCapture:
    """Verify print() output is captured correctly."""

    def test_simple_print(self, executor):
        """Basic print() should be captured."""
        result = executor.execute('print("hello world")')
        assert result.success
        assert result.stdout == "hello world\n"

    def test_multiple_prints(self, executor):
        """Multiple print() calls should all be captured."""
        result = executor.execute(
            'print("line1")\n'
            'print("line2")\n'
            'print("line3")'
        )
        assert result.success
        assert result.stdout == "line1\nline2\nline3\n"

    def test_json_dumps_in_print(self, executor):
        """json.dumps() should work inside print()."""
        result = executor.execute(
            'data = {"key": "value", "num": 42}\n'
            'print(json.dumps(data))'
        )
        assert result.success
        parsed = json.loads(result.stdout.strip())
        assert parsed["key"] == "value"
        assert parsed["num"] == 42

    def test_no_print_empty_output(self, executor):
        """No print() calls should result in empty stdout."""
        result = executor.execute('x = 1 + 1')
        assert result.success
        assert result.stdout == ""


# ── Timeout tests ─────────────────────────────────────────────────── #

class TestTimeout:
    """Verify timeout enforcement."""

    def test_infinite_loop_times_out(self):
        """Infinite loop should be killed after timeout."""
        executor = PTCExecutor(tool_handlers={}, timeout=1.0)
        result = executor.execute("while True: pass")
        assert not result.success
        assert "timed out" in result.error.lower()
        assert result.error_type == "TimeoutError"


# ── Error handling tests ──────────────────────────────────────────── #

class TestErrorHandling:
    """Verify error reporting."""

    def test_syntax_error(self, executor):
        """Syntax errors should be reported."""
        result = executor.execute("def f(:\n  pass")
        assert not result.success
        assert result.error_type == "SyntaxError"

    def test_runtime_error(self, executor):
        """Runtime errors should be reported."""
        result = executor.execute("x = 1 / 0")
        assert not result.success
        assert result.error_type == "ZeroDivisionError"

    def test_name_error(self, executor):
        """Accessing undefined names should be reported."""
        result = executor.execute("print(undefined_variable)")
        assert not result.success
        assert result.error_type == "NameError"

    def test_empty_code(self, executor):
        """Empty code should fail gracefully."""
        result = executor.execute("")
        assert not result.success
        assert result.error_type == "ValueError"

    def test_whitespace_only_code(self, executor):
        """Whitespace-only code should fail gracefully."""
        result = executor.execute("   \n  \n  ")
        assert not result.success
        assert result.error_type == "ValueError"

    def test_output_before_error(self, executor):
        """stdout captured before error should still be available."""
        result = executor.execute(
            'print("before")\n'
            'x = 1 / 0'
        )
        assert not result.success
        assert "before" in result.stdout


# ── Safe builtins tests ───────────────────────────────────────────── #

class TestSafeBuiltins:
    """Verify that safe builtins work correctly."""

    def test_range_and_len(self, executor):
        """range() and len() should work."""
        result = executor.execute(
            'items = list(range(5))\n'
            'print(len(items))'
        )
        assert result.success
        assert result.stdout.strip() == "5"

    def test_list_comprehension(self, executor):
        """List comprehensions should work."""
        result = executor.execute(
            'squares = [x * x for x in range(5)]\n'
            'print(squares)'
        )
        assert result.success
        assert result.stdout.strip() == "[0, 1, 4, 9, 16]"

    def test_dict_construction(self, executor):
        """Dict comprehensions should work."""
        result = executor.execute(
            'd = {str(i): i * 2 for i in range(3)}\n'
            'print(json.dumps(d))'
        )
        assert result.success
        parsed = json.loads(result.stdout.strip())
        assert parsed == {"0": 0, "1": 2, "2": 4}

    def test_try_except(self, executor):
        """try/except should work."""
        result = executor.execute(
            'try:\n'
            '    x = 1 / 0\n'
            'except ZeroDivisionError:\n'
            '    print("caught")'
        )
        assert result.success
        assert result.stdout.strip() == "caught"

    def test_sorted_min_max(self, executor):
        """sorted(), min(), max() should work."""
        result = executor.execute(
            'items = [3, 1, 4, 1, 5]\n'
            'print(sorted(items))\n'
            'print(min(items))\n'
            'print(max(items))'
        )
        assert result.success
        lines = result.stdout.strip().split("\n")
        assert lines[0] == "[1, 1, 3, 4, 5]"
        assert lines[1] == "1"
        assert lines[2] == "5"


# ── End-to-end orchestration test ─────────────────────────────────── #

class TestEndToEnd:
    """Test full PTC workflow: search → details → build pipeline."""

    def test_search_and_build_pipeline(self, executor):
        """Full orchestration: search for skills, get details, build pipeline."""
        code = '''
results = search_skills("cinematic")
top_skill = results["matches"][0]["name"]
details = get_skill_details(top_skill)
params = {"intensity": details["params"]["intensity"]["default"]}
pipeline = build_pipeline(
    [{"name": top_skill, "params": params}],
    "/tmp/input.mp4",
    "/tmp/output.mp4"
)
output = {
    "skill_used": top_skill,
    "params": params,
    "command": pipeline["command"],
    "success": pipeline["success"],
}
print(json.dumps(output))
'''
        result = executor.execute(code)
        assert result.success, f"Execution failed: {result.error}"
        data = json.loads(result.stdout.strip())
        assert data["skill_used"] == "cinematic_grade"
        assert data["params"]["intensity"] == "medium"
        assert data["success"] is True
        assert "ffmpeg" in data["command"]

    def test_multi_skill_pipeline(self, executor):
        """Build a pipeline with multiple skills from search results."""
        code = '''
results = search_skills("cinematic")
skills_to_use = []
for skill_info in results["matches"]:
    details = get_skill_details(skill_info["name"])
    skills_to_use.append({
        "name": details["name"],
        "params": {}
    })
pipeline = build_pipeline(skills_to_use, "/tmp/in.mp4", "/tmp/out.mp4")
print(json.dumps({"count": len(skills_to_use), "success": pipeline["success"]}))
'''
        result = executor.execute(code)
        assert result.success, f"Execution failed: {result.error}"
        data = json.loads(result.stdout.strip())
        assert data["count"] == 2
        assert data["success"] is True

    def test_conditional_logic(self, executor):
        """LLM-style conditional logic in orchestration code."""
        code = '''
results = search_skills("cinematic")
if results["match_count"] > 0:
    best = results["matches"][0]
    print(json.dumps({"found": True, "skill": best["name"]}))
else:
    print(json.dumps({"found": False}))
'''
        result = executor.execute(code)
        assert result.success
        data = json.loads(result.stdout.strip())
        assert data["found"] is True
        assert data["skill"] == "cinematic_grade"


# ── Vision integration tests ──────────────────────────────────────── #

def _mock_extract_frames(
    video_path="/tmp/test.mp4", start=0.0, duration=5.0,
    fps=1.0, max_frames=8,
):
    """Mock extract_frames returning fake frame paths."""
    count = min(int(duration * fps), max_frames)
    paths = [f"/tmp/frames/frame_{i}.png" for i in range(count)]
    return {
        "paths": paths,
        "run_id": "test_run_123",
        "count": len(paths),
    }


class TestVisionIntegration:
    """Verify extract_frames frame path collection via side-channel."""

    @pytest.fixture
    def vision_executor(self):
        """Executor with extract_frames available."""
        collected = []

        def _tracking_extract(video_path="/tmp/test.mp4", start=0.0,
                              duration=5.0, fps=1.0, max_frames=8):
            result = _mock_extract_frames(video_path, start, duration, fps, max_frames)
            if result.get("paths"):
                collected.extend(result["paths"])
            return result

        executor = PTCExecutor(
            tool_handlers={
                "search_skills": _mock_search_skills,
                "get_skill_details": _mock_get_skill_details,
                "extract_frames": _tracking_extract,
            },
            timeout=5.0,
        )
        # Expose collected list for assertions
        executor._test_collected = collected
        return executor

    def test_frame_paths_collected(self, vision_executor):
        """extract_frames inside PTC should collect frame paths."""
        result = vision_executor.execute(
            'frames = extract_frames("/tmp/test.mp4", start=0.0, duration=3.0, fps=1.0)\n'
            'print(frames["count"])'
        )
        assert result.success
        assert result.stdout.strip() == "3"
        # The side-channel list should have frame paths
        assert len(vision_executor._test_collected) == 3
        assert all("/tmp/frames/frame_" in p for p in vision_executor._test_collected)

    def test_frame_paths_empty_when_no_extract(self, vision_executor):
        """frame_paths should be empty when extract_frames is not called."""
        result = vision_executor.execute(
            'skills = search_skills("blur")\n'
            'print(skills["match_count"])'
        )
        assert result.success
        assert len(vision_executor._test_collected) == 0

    def test_extract_frames_with_orchestration(self, vision_executor):
        """extract_frames combined with other tools in one PTC script."""
        code = '''
frames = extract_frames("/tmp/test.mp4", duration=2.0, fps=1.0)
results = search_skills("cinematic")
details = get_skill_details(results["matches"][0]["name"])
output = {
    "frames_extracted": frames["count"],
    "skill": details["name"],
}
print(json.dumps(output))
'''
        result = vision_executor.execute(code)
        assert result.success, f"Execution failed: {result.error}"
        data = json.loads(result.stdout.strip())
        assert data["frames_extracted"] == 2
        assert data["skill"] == "cinematic_grade"
        assert len(vision_executor._test_collected) == 2

