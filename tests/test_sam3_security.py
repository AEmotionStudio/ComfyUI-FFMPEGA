import pytest
import os
import sys
import subprocess
import tempfile
import json
from unittest.mock import patch, MagicMock

class TestSAM3Security:
    def test_subprocess_receives_downloads_flag(self):
        """Test that the SAM3 subprocess correctly receives and applies the downloads flag
        without triggering core/__init__.py dependencies like pydantic."""

        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        mod_path = os.path.join(project_root, "core", "sam3_masker.py")

        with open(mod_path, "r") as f:
            src = f.read()

        script_start = src.find('child_script = """') + len('child_script = """')
        script_end = src.find('"""', script_start)
        child_script = src[script_start:script_end].strip()

        # We replace the actual execution of sam3_masker to avoid needing numpy etc for this test
        # We only care that model_manager.set_downloads_allowed works and that we bypassed core.__init__
        test_script = child_script.replace("spec = importlib.util.spec_from_file_location(\"sam3_masker\", mod_path)", "#")
        test_script = test_script.replace("mod = importlib.util.module_from_spec(spec)", "#")
        test_script = test_script.replace("spec.loader.exec_module(mod)", "#")
        test_script = test_script.replace("result = mod.mask_video(**args)", "result = 'RESULT:/tmp/fake.mp4'")
        test_script += """
print(f"TEST_OK: downloads_allowed={model_manager.downloads_allowed()}")
"""

        args_dict = {
            "video_path": "fake",
            "prompt": "fake",
            "_allow_downloads": False,
            "_module_path": mod_path
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(test_script)
            tmp_path = f.name

        try:
            cmd = [sys.executable, tmp_path]
            env = os.environ.copy()

            result = subprocess.run(
                cmd,
                input=json.dumps(args_dict),
                text=True,
                capture_output=True,
                env=env,
                cwd=project_root
            )

            assert result.returncode == 0, f"Child script failed: {result.stderr}\nStdout: {result.stdout}"
            assert "TEST_OK: downloads_allowed=False" in result.stdout
        finally:
            os.unlink(tmp_path)
