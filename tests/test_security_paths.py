"""Security tests for the consolidated path sandbox and the file-read guards.

Unlike tests/test_preset_and_sandbox.py (which re-expresses the rule), these
import and drive the *real* functions, so a regression in the actual code is
caught. Covers:

* the single authority `loadlast.discovery.path_utils.is_path_sandboxed`
  (torch-free);
* the watermark `movie=` file-read guard in the video editor (torch-free);
* the `/facepoke/*` and `/framepicker/*` route resolvers, which must not
  return an out-of-sandbox absolute path (needs torch — the node modules import
  it at module scope — so guarded with importorskip).
"""

from __future__ import annotations

import os
import sys
import tempfile
import types

import pytest


@pytest.fixture(autouse=True)
def pinned_dirs(monkeypatch, tmp_path):
    """Pin folder_paths to known dirs for the duration of each test.

    The two conftest folder_paths stubs disagree (the root one defines only
    get_output_directory) and which is active depends on collection order, so
    tests here set their own sandbox boundary rather than trusting whichever
    stub won. Crucially, ``path_utils`` binds ``folder_paths`` **once at import**
    — which may be a different object than ``sys.modules["folder_paths"]`` later
    in a full run — so we patch the reference path_utils actually holds.
    """
    from loadlast.discovery import path_utils

    fp = path_utils.folder_paths
    if fp is None:
        fp = types.ModuleType("folder_paths")
        monkeypatch.setattr(path_utils, "folder_paths", fp)
    out, tmp, inp = tmp_path / "output", tmp_path / "temp", tmp_path / "input"
    for d in (out, tmp, inp):
        d.mkdir(exist_ok=True)
    monkeypatch.setattr(fp, "get_output_directory", lambda: str(out), raising=False)
    monkeypatch.setattr(fp, "get_temp_directory", lambda: str(tmp), raising=False)
    monkeypatch.setattr(fp, "get_input_directory", lambda: str(inp), raising=False)
    # Keep sys.modules aligned so anything importing folder_paths fresh agrees.
    monkeypatch.setitem(sys.modules, "folder_paths", fp)
    return {"output": str(out), "temp": str(tmp), "input": str(inp)}


# ---------------------------------------------------------------------------
#  The single authority: path_utils.is_path_sandboxed
# ---------------------------------------------------------------------------

from loadlast.discovery.path_utils import is_path_sandboxed


class TestSandboxAuthority:
    def test_comfyui_output_dir_is_allowed(self, pinned_dirs):
        assert is_path_sandboxed(os.path.join(pinned_dirs["output"], "render.mp4"))

    def test_comfyui_input_dir_is_allowed(self, pinned_dirs):
        assert is_path_sandboxed(os.path.join(pinned_dirs["input"], "clip.mp4"))

    def test_ffmpega_scratch_dir_is_allowed(self):
        d = tempfile.mkdtemp(prefix="ffmpega_")
        try:
            assert is_path_sandboxed(os.path.join(d, "clip_preview.mp4"))
        finally:
            os.rmdir(d)

    def test_ffmpega_prefixed_file_directly_in_tempdir_is_allowed(self):
        # e.g. ffmpega_preview_xxx.mp4 written straight into the tempdir
        sys_tmp = os.path.realpath(tempfile.gettempdir())
        assert is_path_sandboxed(os.path.join(sys_tmp, "ffmpega_preview_x.mp4"))

    def test_unrelated_tempdir_file_is_rejected(self):
        sys_tmp = os.path.realpath(tempfile.gettempdir())
        assert not is_path_sandboxed(os.path.join(sys_tmp, "someone_elses_xyz123.mp4"))

    def test_unrelated_tempdir_subdir_is_rejected(self):
        sys_tmp = os.path.realpath(tempfile.gettempdir())
        assert not is_path_sandboxed(os.path.join(sys_tmp, "other_xyz123", "clip.mp4"))

    def test_tempdir_itself_is_rejected(self):
        assert not is_path_sandboxed(tempfile.gettempdir())

    def test_prefix_must_be_a_whole_segment(self):
        # a sibling dir that merely starts with the substring must not pass
        sys_tmp = os.path.realpath(tempfile.gettempdir())
        assert not is_path_sandboxed(os.path.join(sys_tmp, "notffmpega_xyz", "x.mp4"))

    def test_absolute_outside_path_is_rejected(self):
        assert not is_path_sandboxed("/etc/passwd")

    def test_traversal_out_of_scratch_is_rejected(self):
        # realpath collapses '..', so this escapes the ffmpega_ dir
        d = tempfile.mkdtemp(prefix="ffmpega_")
        try:
            assert not is_path_sandboxed(os.path.join(d, "..", "..", "etc", "passwd"))
        finally:
            os.rmdir(d)

    def test_missing_getter_does_not_crash(self, monkeypatch):
        """A partial folder_paths must degrade, not raise (the latent bug)."""
        from loadlast.discovery import path_utils
        fp = sys.modules["folder_paths"]
        monkeypatch.delattr(fp, "get_temp_directory", raising=False)
        monkeypatch.delattr(fp, "get_input_directory", raising=False)
        dirs = path_utils.get_allowed_directories()  # must not raise
        assert any("output" in d for d in dirs)      # the surviving getter
        assert not is_path_sandboxed("/etc/passwd")  # still rejects outside


# ---------------------------------------------------------------------------
#  Watermark movie= file-read guard (finding #1)
# ---------------------------------------------------------------------------

from videoeditor.processing.compose import build_watermark_filter


class TestWatermarkPathGuard:
    def test_out_of_sandbox_path_disables_watermark(self):
        """An absolute path outside the sandbox must yield no filter at all."""
        result = build_watermark_filter({"enabled": True, "path": "/etc/hosts"})
        assert result is None

    def test_sandboxed_path_builds_a_filter(self, pinned_dirs):
        result = build_watermark_filter(
            {"enabled": True, "path": os.path.join(pinned_dirs["input"], "logo.png")}
        )
        assert result is not None
        assert "movie=" in result

    def test_disabled_is_none_regardless(self):
        assert build_watermark_filter({"enabled": False, "path": "/etc/hosts"}) is None

    def test_empty_path_is_none(self):
        assert build_watermark_filter({"enabled": True, "path": ""}) is None


# ---------------------------------------------------------------------------
#  Route resolvers must not return out-of-sandbox absolute paths (finding #2)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("module_name", [
    "nodes.facepoke_node",
    "nodes.frame_picker_node",
])
class TestRouteResolverGuard:
    """The /facepoke/* and /framepicker/* routes call these module-level
    resolvers directly, bypassing the node's own process() sandbox check."""

    def _resolver(self, module_name):
        pytest.importorskip("torch")  # node modules import torch at module scope
        import importlib
        mod = importlib.import_module(module_name)
        return mod._resolve_video_path

    def test_arbitrary_absolute_file_is_refused(self, module_name):
        resolve = self._resolver(module_name)
        # a real, readable file that exists well outside any sandbox dir
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            outside = f.name  # e.g. /tmp/tmpXXXX.mp4 — not ffmpega_-prefixed
        try:
            assert resolve(outside) is None
        finally:
            os.unlink(outside)

    def test_ffmpega_scratch_file_is_returned(self, module_name):
        resolve = self._resolver(module_name)
        d = tempfile.mkdtemp(prefix="ffmpega_")
        p = os.path.join(d, "clip.mp4")
        with open(p, "wb") as f:
            f.write(b"\x00")
        try:
            assert resolve(p) == p
        finally:
            os.unlink(p)
            os.rmdir(d)

    def test_empty_is_none(self, module_name):
        resolve = self._resolver(module_name)
        assert resolve("") is None
