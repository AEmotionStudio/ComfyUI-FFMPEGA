"""Tests for the tempdir sandbox rule and preset payload validation.

``server.py`` cannot be imported here — it uses relative imports that need
ComfyUI's package context, which is why ``tests/test_server_routes.py``
tests route *logic* rather than the routes themselves. These tests follow
that convention: they re-express the rules the handlers apply and pin the
behaviour that matters, so a regression in intent is visible even though
the module itself is not exercised.
"""

from __future__ import annotations

import json
import os
import tempfile

import pytest


# ---------------------------------------------------------------------------
#  Tempdir sandbox rule (server._is_path_sandboxed)
# ---------------------------------------------------------------------------


def _tempdir_segment_allowed(path: str) -> bool:
    """The rule server.py applies to paths under the system temp directory.

    Only FFMPEGA's own scratch space counts: the first path segment beneath
    the tempdir must start with ``ffmpega_``.
    """
    real = os.path.realpath(path)
    sys_tmp = os.path.realpath(tempfile.gettempdir())
    if not real.startswith(sys_tmp + os.sep):
        return False
    first_segment = real[len(sys_tmp) + 1:].split(os.sep)[0]
    return first_segment.startswith("ffmpega_")


class TestTempdirSandbox:
    """The route previously served anything under /tmp; now it does not."""

    @pytest.fixture
    def tmp_root(self):
        return os.path.realpath(tempfile.gettempdir())

    def test_ffmpega_render_dir_is_allowed(self, tmp_root):
        """nodes/output_handler.py renders previews into mkdtemp(prefix="ffmpega_")."""
        assert _tempdir_segment_allowed(
            os.path.join(tmp_root, "ffmpega_ab12cd", "clip_preview.mp4")
        )

    def test_ffmpega_preview_transcode_is_allowed(self, tmp_root):
        """server.py writes transcodes as ffmpega_preview_*.mp4."""
        assert _tempdir_segment_allowed(
            os.path.join(tmp_root, "ffmpega_preview_xyz.mp4")
        )

    def test_ffmpega_first_frame_is_allowed(self, tmp_root):
        """server.py extracts first frames as ffmpega_frame_*.png."""
        assert _tempdir_segment_allowed(
            os.path.join(tmp_root, "ffmpega_frame_001.png")
        )

    def test_unrelated_tempdir_file_is_rejected(self, tmp_root):
        """Another process's file under /tmp is not ours to serve."""
        assert not _tempdir_segment_allowed(os.path.join(tmp_root, "secrets.mp4"))

    def test_unrelated_tempdir_subdir_is_rejected(self, tmp_root):
        assert not _tempdir_segment_allowed(
            os.path.join(tmp_root, "someone_else", "video.mp4")
        )

    def test_prefix_must_be_a_whole_segment(self, tmp_root):
        """A sibling directory merely *containing* the name must not pass."""
        assert not _tempdir_segment_allowed(
            os.path.join(tmp_root, "not_ffmpega_stuff", "video.mp4")
        )

    def test_tempdir_itself_is_rejected(self, tmp_root):
        assert not _tempdir_segment_allowed(tmp_root)

    def test_path_outside_tempdir_is_rejected(self):
        assert not _tempdir_segment_allowed("/etc/passwd")

    def test_traversal_out_of_ffmpega_dir_is_rejected(self, tmp_root):
        """realpath collapses '..', so traversal cannot escape the check."""
        assert not _tempdir_segment_allowed(
            os.path.join(tmp_root, "ffmpega_ab12cd", "..", "..", "etc", "passwd")
        )


# ---------------------------------------------------------------------------
#  Preset payload validation (server._write_presets)
# ---------------------------------------------------------------------------

_PRESET_MAX_BYTES = 256 * 1024
_PRESET_MAX_ITEMS = 500


def _validate_preset_payload(raw: bytes) -> tuple[bool, str]:
    """The checks _write_presets runs before writing anything to disk."""
    if len(raw) > _PRESET_MAX_BYTES:
        return False, "payload too large"
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return False, "invalid JSON"
    if not isinstance(data, list):
        return False, "expected array"
    if len(data) > _PRESET_MAX_ITEMS:
        return False, "too many presets"
    for item in data:
        if not isinstance(item, dict):
            return False, "each preset must be an object"
        if not all(isinstance(k, str) for k in item):
            return False, "preset keys must be strings"
    return True, ""


class TestPresetValidation:
    def test_valid_payload_accepted(self):
        raw = json.dumps([{"name": "Title", "size": 48}]).encode()
        assert _validate_preset_payload(raw)[0]

    def test_empty_list_accepted(self):
        assert _validate_preset_payload(b"[]")[0]

    def test_oversized_payload_rejected(self):
        raw = json.dumps([{"a": "x" * (_PRESET_MAX_BYTES)}]).encode()
        ok, err = _validate_preset_payload(raw)
        assert not ok and err == "payload too large"

    def test_malformed_json_rejected(self):
        ok, err = _validate_preset_payload(b"{not json")
        assert not ok and err == "invalid JSON"

    def test_non_array_rejected(self):
        ok, err = _validate_preset_payload(b'{"name": "x"}')
        assert not ok and err == "expected array"

    def test_too_many_items_rejected(self):
        raw = json.dumps([{"n": i} for i in range(_PRESET_MAX_ITEMS + 1)]).encode()
        ok, err = _validate_preset_payload(raw)
        assert not ok and err == "too many presets"

    def test_non_object_items_rejected(self):
        ok, err = _validate_preset_payload(b'["just a string"]')
        assert not ok and err == "each preset must be an object"

    def test_invalid_utf8_rejected(self):
        ok, err = _validate_preset_payload(b"\xff\xfe not utf-8")
        assert not ok and err == "invalid JSON"
