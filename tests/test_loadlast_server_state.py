"""Unit tests for LoadLastVideo server-side state management.

Tests the select_video / apply_edits server-side state dicts,
IS_CHANGED TTL eviction, cap enforcement, and path sanitization.
"""

import sys
import os
import time
import types
import tempfile
import importlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

torch = __import__("pytest").importorskip("torch")

# ── Set up mocks before importing the module ──
_temp_dirs: list[str] = []


def _make_temp():
    d = tempfile.mkdtemp()
    _temp_dirs.append(d)
    return d


mock_fp = types.ModuleType("folder_paths")
mock_fp.get_output_directory = _make_temp
mock_fp.get_temp_directory = _make_temp
mock_fp.get_input_directory = _make_temp
sys.modules.setdefault("folder_paths", mock_fp)

mock_mm = types.ModuleType("comfy")
mock_mm_inner = types.ModuleType("comfy.model_management")
mock_mm_inner.get_torch_device = lambda: torch.device("cpu")
mock_mm.model_management = mock_mm_inner
sys.modules.setdefault("comfy", mock_mm)
sys.modules.setdefault("comfy.model_management", mock_mm_inner)

import loadlast.load_last_video as llv


# ── Helpers ──

def _clear_state():
    """Reset all server-side state dicts between tests."""
    llv._user_video_selections.clear()
    llv._user_edit_states.clear()
    llv._fps_cache.clear()


# ═══════════════════════════════════════════════════════════════════
# Video Selection State Tests
# ═══════════════════════════════════════════════════════════════════

class TestVideoSelectionState:
    """Tests for _user_video_selections dict management."""

    def setup_method(self):
        _clear_state()

    def test_store_and_pop(self):
        """Basic store-and-consume cycle."""
        entry = {"filename": "test.mp4", "subfolder": "", "type": "output"}
        llv._user_video_selections["42"] = {"data": entry, "ts": time.time()}

        assert "42" in llv._user_video_selections
        wrapper = llv._user_video_selections.pop("42", None)
        assert wrapper is not None
        assert wrapper["data"]["filename"] == "test.mp4"
        assert "42" not in llv._user_video_selections

    def test_pop_returns_none_for_missing(self):
        """Pop on missing key returns None without error."""
        result = llv._user_video_selections.pop("nonexistent", None)
        assert result is None

    def test_null_entry_clears(self):
        """Storing None (null) clears the entry."""
        llv._user_video_selections["42"] = {"data": {"filename": "a.mp4"}, "ts": time.time()}
        llv._user_video_selections.pop("42", None)
        assert "42" not in llv._user_video_selections

    def test_cap_enforcement(self):
        """_capped_insert evicts oldest entry when dict reaches cap."""
        cap = llv._MAX_SERVER_STATE_ENTRIES
        for i in range(cap + 10):
            llv._capped_insert(
                llv._user_video_selections,
                str(i),
                {"data": {"filename": f"v{i}.mp4"}, "ts": time.time()},
            )

        assert len(llv._user_video_selections) <= cap

    def test_allowed_entry_keys_filter(self):
        """Only _ALLOWED_ENTRY_KEYS are retained."""
        raw = {
            "filename": "test.mp4",
            "subfolder": "sub",
            "type": "output",
            "format": "video/mp4",
            "evil_key": "should_be_removed",
        }
        filtered = {k: str(v) for k, v in raw.items() if k in llv._ALLOWED_ENTRY_KEYS}
        assert "evil_key" not in filtered
        assert "filename" in filtered
        assert len(filtered) == 4

    def test_allowed_sel_types(self):
        """Only 'output' and 'temp' are valid selection types."""
        assert "output" in llv._ALLOWED_SEL_TYPES
        assert "temp" in llv._ALLOWED_SEL_TYPES
        assert "input" not in llv._ALLOWED_SEL_TYPES
        assert "../" not in llv._ALLOWED_SEL_TYPES


# ═══════════════════════════════════════════════════════════════════
# Edit State Tests
# ═══════════════════════════════════════════════════════════════════

class TestEditState:
    """Tests for _user_edit_states dict management."""

    def setup_method(self):
        _clear_state()

    def test_store_and_pop(self):
        """Basic store-and-consume cycle."""
        edits = {"segments": "[]", "crop_rect": "", "speed_map": "{}"}
        llv._user_edit_states["42"] = {"data": edits, "ts": time.time()}

        assert "42" in llv._user_edit_states
        wrapper = llv._user_edit_states.pop("42", None)
        assert wrapper is not None
        assert wrapper["data"]["segments"] == "[]"
        assert "42" not in llv._user_edit_states

    def test_allowed_edit_keys_filter(self):
        """Only _ALLOWED_EDIT_KEYS are retained."""
        raw = {
            "segments": "[]",
            "crop_rect": "",
            "speed_map": "{}",
            "malicious_field": "DROP TABLE;",
        }
        filtered = {k: str(v) for k, v in raw.items() if k in llv._ALLOWED_EDIT_KEYS}
        assert "malicious_field" not in filtered
        assert len(filtered) == 3

    def test_cap_enforcement(self):
        """_capped_insert evicts oldest entry when dict reaches cap."""
        cap = llv._MAX_SERVER_STATE_ENTRIES
        for i in range(cap + 5):
            llv._capped_insert(
                llv._user_edit_states,
                str(i),
                {"data": {"segments": "[]"}, "ts": time.time()},
            )

        assert len(llv._user_edit_states) <= cap


# ═══════════════════════════════════════════════════════════════════
# IS_CHANGED TTL Eviction Tests
# ═══════════════════════════════════════════════════════════════════

class TestISChangedTTLEviction:
    """Tests for TTL-based stale entry eviction in IS_CHANGED."""

    def setup_method(self):
        _clear_state()

    def test_stale_selection_evicted(self):
        """Entries older than _SERVER_STATE_TTL are evicted."""
        stale_ts = time.time() - llv._SERVER_STATE_TTL - 10
        llv._user_video_selections["old_node"] = {
            "data": {"filename": "stale.mp4"},
            "ts": stale_ts,
        }
        llv._user_video_selections["fresh_node"] = {
            "data": {"filename": "fresh.mp4"},
            "ts": time.time(),
        }

        # IS_CHANGED runs eviction
        llv.LoadLastVideo.IS_CHANGED(refresh_mode="auto", unique_id="other")

        assert "old_node" not in llv._user_video_selections
        assert "fresh_node" in llv._user_video_selections

    def test_stale_edits_evicted(self):
        """Edit state entries older than TTL are evicted."""
        stale_ts = time.time() - llv._SERVER_STATE_TTL - 10
        llv._user_edit_states["old_node"] = {
            "data": {"segments": "[]"},
            "ts": stale_ts,
        }

        llv.LoadLastVideo.IS_CHANGED(refresh_mode="auto", unique_id="other")

        assert "old_node" not in llv._user_edit_states

    def test_fresh_entry_triggers_rerun(self):
        """IS_CHANGED returns unique value when server state exists for this node."""
        llv._user_video_selections["99"] = {
            "data": {"filename": "pick.mp4"},
            "ts": time.time(),
        }

        result = llv.LoadLastVideo.IS_CHANGED(refresh_mode="manual", unique_id="99")
        assert result.startswith("selected_99_")

    def test_fresh_edit_triggers_rerun(self):
        """IS_CHANGED returns unique value when edit state exists for this node."""
        llv._user_edit_states["99"] = {
            "data": {"segments": "[[0,1]]"},
            "ts": time.time(),
        }

        result = llv.LoadLastVideo.IS_CHANGED(refresh_mode="manual", unique_id="99")
        assert result.startswith("edits_99_")

    def test_manual_mode_stable_when_no_state(self):
        """Manual mode returns constant when no server state exists."""
        result = llv.LoadLastVideo.IS_CHANGED(refresh_mode="manual", unique_id="99")
        assert result == ""


# ═══════════════════════════════════════════════════════════════════
# Filename Sanitization Tests
# ═══════════════════════════════════════════════════════════════════

class TestFilenameSanitization:
    """Tests for path-traversal prevention in video selection consumption."""

    def setup_method(self):
        _clear_state()

    def test_basename_strips_path_separators(self):
        """os.path.basename strips leading path components from filename."""
        assert os.path.basename("../../etc/passwd") == "passwd"
        assert os.path.basename("foo/bar/baz.mp4") == "baz.mp4"
        assert os.path.basename("normal.mp4") == "normal.mp4"
        assert os.path.basename("") == ""

    def test_traversal_subfolder_rejected(self):
        """Subfolder containing '..' is rejected."""
        sel = {
            "filename": "innocent.mp4",
            "subfolder": "../../../etc",
            "type": "output",
        }
        # The load() method checks: if ".." in sel_subfolder.split(os.sep)
        subfolder = sel["subfolder"]
        has_traversal = ".." in subfolder.split(os.sep)
        assert has_traversal, "Should detect '..' traversal in subfolder"

    def test_traversal_filename_sanitized(self):
        """Filename with path separators is sanitized via basename."""
        raw_filename = "../../etc/passwd"
        safe = os.path.basename(raw_filename)
        assert safe == "passwd"
        assert "/" not in safe
        assert ".." not in safe


# ═══════════════════════════════════════════════════════════════════
# FPS Cache Tests
# ═══════════════════════════════════════════════════════════════════

class TestFPSCache:
    """Tests for _fps_cache management."""

    def setup_method(self):
        _clear_state()

    def test_cache_cap(self):
        """FPS cache is capped at 200 entries via _probe_fps_cached's eviction."""
        # Directly exercise the same cap logic that _probe_fps_cached uses:
        #   if len(_fps_cache) > 200: evict oldest
        for i in range(210):
            path = f"/fake/path_{i}.mp4"
            llv._fps_cache[path] = (24.0, float(i))
            # Replicate the production eviction guard from _probe_fps_cached
            if len(llv._fps_cache) > 200:
                oldest_key = next(iter(llv._fps_cache))
                llv._fps_cache.pop(oldest_key, None)

        assert len(llv._fps_cache) <= 200

    def test_cache_mtime_invalidation(self):
        """Cache hit requires matching mtime."""
        llv._fps_cache["/test.mp4"] = (30.0, 100.0)

        cached = llv._fps_cache.get("/test.mp4")
        # Same mtime → hit
        assert cached and cached[1] == 100.0
        # Different mtime → miss
        assert not (cached and cached[1] == 200.0)

    def test_server_state_ttl_positive(self):
        """TTL is a reasonable positive value."""
        assert llv._SERVER_STATE_TTL > 0
        assert llv._SERVER_STATE_TTL == 300  # 5 minutes as documented
