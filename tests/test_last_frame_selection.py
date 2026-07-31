"""Tests for the torch-free tail-selection and slot-naming logic.

These cover the edge cases that decide whether a continuation chain keeps
working: an offset past the start of a short clip, an empty batch, and slot
names that try to escape the output directory.
"""

import os

from core.last_frame import (
    DEFAULT_SLOT,
    LAST_FRAME_ROOT,
    frame_name,
    sanitize_slot,
    select_tail_indices,
    slot_prefix,
)


class TestSelectTailIndices:
    """Tail indices are chronological and clamp instead of raising."""

    def test_single_last_frame(self):
        assert select_tail_indices(10, 1, 0) == [9]

    def test_multiple_frames_are_chronological(self):
        # Oldest first — a batch feeding a video model must not be reversed.
        assert select_tail_indices(10, 3, 0) == [7, 8, 9]

    def test_offset_skips_the_tail(self):
        assert select_tail_indices(10, 3, 2) == [5, 6, 7]

    def test_offset_of_one_picks_second_to_last(self):
        assert select_tail_indices(10, 1, 1) == [8]

    def test_single_frame_video(self):
        assert select_tail_indices(1, 1, 0) == [0]

    def test_count_larger_than_total_returns_everything(self):
        assert select_tail_indices(1, 4, 0) == [0]
        assert select_tail_indices(3, 10, 0) == [0, 1, 2]

    def test_offset_past_start_clamps_to_first_frame(self):
        # Clamping beats raising: failing at the end of a long chain is worse
        # than quietly using the only frame available.
        assert select_tail_indices(5, 2, 99) == [0]

    def test_empty_batch_returns_nothing(self):
        # Must be empty, never [0] — callers treat [] as "write nothing".
        assert select_tail_indices(0, 1, 0) == []

    def test_negative_total_returns_nothing(self):
        assert select_tail_indices(-3, 1, 0) == []

    def test_negative_inputs_are_coerced(self):
        assert select_tail_indices(10, -5, -5) == [9]


class TestSanitizeSlot:
    """Slot names are the path-traversal defense."""

    def test_traversal_is_stripped(self):
        result = sanitize_slot("../../etc")
        assert ".." not in result
        assert "/" not in result and "\\" not in result

    def test_absolute_path_is_stripped(self):
        result = sanitize_slot("/etc/passwd")
        assert not os.path.isabs(result)
        assert "/" not in result

    def test_empty_falls_back_to_default(self):
        assert sanitize_slot("") == DEFAULT_SLOT
        assert sanitize_slot("   ") == DEFAULT_SLOT
        assert sanitize_slot("///") == DEFAULT_SLOT

    def test_non_string_falls_back_to_default(self):
        assert sanitize_slot(None) == DEFAULT_SLOT
        assert sanitize_slot(42) == DEFAULT_SLOT

    def test_ordinary_names_survive_intact(self):
        assert sanitize_slot("drone_a") == "drone_a"
        assert sanitize_slot("shot-01") == "shot-01"

    def test_spaces_become_underscores(self):
        assert sanitize_slot("my drone shot") == "my_drone_shot"


class TestSlotPrefix:
    def test_prefix_shape(self):
        assert slot_prefix("drone", "lastframe") == f"{LAST_FRAME_ROOT}/drone/lastframe"

    def test_prefix_sanitizes_both_parts(self):
        result = slot_prefix("../evil", "../bad")
        assert ".." not in result
        assert result.count("/") == 2

    def test_default_prefix(self):
        assert slot_prefix("drone").endswith("/lastframe")


class TestFrameName:
    def test_zero_padded_so_filename_sort_is_chronological(self):
        names = [frame_name(i) for i in range(11)]
        assert names[0] == "lastframe_00.png"
        assert names[10] == "lastframe_10.png"
        # The whole point: lexical order == chronological order.
        assert sorted(names) == names
