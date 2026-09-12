"""Tests for the pinned-revision helper.

These assert that the pin is actually *threaded through* to huggingface_hub,
not merely declared in a table — a pin nobody passes is worse than no pin,
because it reads as protection that isn't there. Nothing here touches the
network; the download functions are replaced with recording fakes.
"""

import sys
import types

import pytest

from core import hf_pins


def _fake_hub(recorder):
    """Install a fake huggingface_hub whose download fns record their kwargs."""
    mod = types.ModuleType("huggingface_hub")

    def hf_hub_download(**kwargs):
        recorder.append(("hf_hub_download", kwargs))
        return "/tmp/ffmpega_fake/file.safetensors"

    def snapshot_download(**kwargs):
        recorder.append(("snapshot_download", kwargs))
        return "/tmp/ffmpega_fake"

    mod.hf_hub_download = hf_hub_download
    mod.snapshot_download = snapshot_download
    return mod


@pytest.fixture
def calls(monkeypatch):
    recorded: list[tuple[str, dict]] = []
    monkeypatch.setitem(sys.modules, "huggingface_hub", _fake_hub(recorded))
    return recorded


class TestRevisionFor:
    def test_third_party_repo_is_pinned(self):
        rev = hf_pins.revision_for("Comfy-Org/SCAIL-2")
        assert rev and len(rev) == 40

    def test_kiwi_edit_repos_are_pinned(self):
        """Kiwi-Edit's directory is executed via trust_remote_code."""
        for repo in (
            "linyq/kiwi-edit-5b-instruct-only-diffusers",
            "linyq/kiwi-edit-5b-reference-only-diffusers",
            "linyq/kiwi-edit-5b-instruct-reference-diffusers",
        ):
            assert hf_pins.revision_for(repo), f"{repo} must be pinned"

    def test_own_mirrors_float(self):
        """AEmotionStudio mirrors are deliberately unpinned."""
        assert hf_pins.revision_for("AEmotionStudio/sam3") is None

    def test_unknown_repo_floats(self):
        assert hf_pins.revision_for("someone/not-in-the-table") is None

    def test_every_pin_is_a_full_sha(self):
        for repo, rev in hf_pins.PINNED_REVISIONS.items():
            assert len(rev) == 40, f"{repo} pin is not a full commit SHA"
            assert all(c in "0123456789abcdef" for c in rev), repo


class TestPinIsPassedThrough:
    def test_pinned_repo_gets_revision(self, calls):
        hf_pins.pinned_hf_download(
            repo_id="Comfy-Org/SCAIL-2", filename="model.safetensors",
        )
        _, kwargs = calls[0]
        assert kwargs["revision"] == hf_pins.revision_for("Comfy-Org/SCAIL-2")

    def test_snapshot_pinned_repo_gets_revision(self, calls):
        repo = "linyq/kiwi-edit-5b-instruct-only-diffusers"
        hf_pins.pinned_snapshot_download(repo_id=repo, local_dir="/tmp/ffmpega_x")
        _, kwargs = calls[0]
        assert kwargs["revision"] == hf_pins.revision_for(repo)

    def test_unpinned_repo_gets_no_revision(self, calls):
        hf_pins.pinned_snapshot_download(
            repo_id="AEmotionStudio/sam3", local_dir="/tmp/ffmpega_x",
        )
        _, kwargs = calls[0]
        assert "revision" not in kwargs

    def test_explicit_revision_wins(self, calls):
        """The pin is a default, not an override."""
        hf_pins.pinned_hf_download(
            repo_id="Comfy-Org/SCAIL-2", filename="m.safetensors", revision="deadbeef",
        )
        _, kwargs = calls[0]
        assert kwargs["revision"] == "deadbeef"

    def test_other_kwargs_survive(self, calls):
        hf_pins.pinned_hf_download(
            repo_id="hkchengrex/MMAudio",
            filename="weights/model.pth",
            local_dir="/tmp/ffmpega_x",
            local_dir_use_symlinks=False,
        )
        _, kwargs = calls[0]
        assert kwargs["filename"] == "weights/model.pth"
        assert kwargs["local_dir"] == "/tmp/ffmpega_x"
        assert kwargs["local_dir_use_symlinks"] is False
