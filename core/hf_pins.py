# coding: utf-8
"""Pinned HuggingFace revisions for third-party model repositories.

Every download from a repository FFMPEGA does not control is pinned to an
exact commit, so a change pushed upstream cannot silently alter what users
receive.  For most repos that means the weights; for Kiwi-Edit it also means
the Python that ``trust_remote_code=True`` later executes out of the
downloaded directory (``core/kiwi_edit_synthesizer.py``), which is why that
repo matters more than its size suggests.

AEmotionStudio mirrors are deliberately **not** pinned.  They are our own
repositories, and pinning them would turn every routine re-upload into a code
change plus a release.  The mechanism is repo-agnostic, so adding one here is
a one-line edit if that ever changes.

``Guoxu1233/DreamID-Omni`` is absent on purpose: the repo is gated (HTTP 401
anonymously), so its revision cannot be resolved without credentials.  It is
only ever the fallback behind the ``AEmotionStudio/dreamid-omni`` mirror.

To refresh a pin, resolve the repo's current head and replace the value::

    git ls-remote https://huggingface.co/<repo_id> HEAD
"""

from __future__ import annotations

import logging
from typing import Any, Callable

log = logging.getLogger("ffmpega")

# repo_id -> exact commit SHA.  Resolved 2026-09-11.
PINNED_REVISIONS: dict[str, str] = {
    # --- Kiwi-Edit: downloaded directory is executed via trust_remote_code ---
    "linyq/kiwi-edit-5b-instruct-only-diffusers": "277f43b7bc84d27d9a3af1a5a7484ba8237b4ac3",
    "linyq/kiwi-edit-5b-reference-only-diffusers": "617c5a600749958ec6f80bb3722a74eb065a96cb",
    "linyq/kiwi-edit-5b-instruct-reference-diffusers": "2760d8197b6bdb49181bce8cceb2da781568b766",

    # --- Third-party weights ---
    "zibojia/minimax-remover": "889e41651d903bcef2d2aea307155812b6d326fd",
    "hkchengrex/MMAudio": "eb13a1a98fdbec91753775c57b074ccdfc60587c",
    "TMElyralab/MuseTalk": "3ef28bc5cff08c90ad8178a25f1b570cd800170f",
    "stabilityai/sd-vae-ft-mse": "31f26fdeee1355a5c34592e401dd41e45d25a493",
    "openai/whisper-tiny": "169d4a4341b33bc18d8881c4b69c2e104e1cc0af",
    "facebook/detr-resnet-101-dc5": "96317ca979e231bd960cb3cac31328e0165a3e94",
    "ACE-Step/Ace-Step1.5": "19671f406d603126926c1b7e2adc169acbcade22",
    "HKUSTAudio/AudioX-MAF": "0a6575a6fd58039281584ad1c6f9e895233e8ca7",
    "Wan-AI/Wan2.2-TI2V-5B": "921dbaf3f1674a56f47e83fb80a34bac8a8f203e",
    "fishaudio/s2-pro": "1de9996b6be38b745688de084d87a5633f714e4e",
    "1038lab/FlashVSR": "f1bc675696d43f05d183d9b7c49e44d84c843caf",
    "RoyalCities/Foundation-1": "7b10fbbbc1be2f54cbc5540aab89ee383bc94e4a",
    "KlingTeam/LivePortrait": "82a4fa6735ca58432b6ce39301b4b9ee066dea47",
    "xiangbog/Visual_Chronometer": "73ecbe22d377a43dba663fc6856dd75c5cd84f87",
    "Comfy-Org/SCAIL-2": "3bd725f20edad6967a65792af3017e251a5bd853",
    "vita-video-gen/svi-model": "f9bdd50c57e4c28f0d088b6bad8afa3fdc3bc1ac",
    "nvidia/bigvgan_v2_44khz_128band_512x": "95a9d1dcb12906c03edd938d77b9333d6ded7dfb",
}


def revision_for(repo_id: str) -> str | None:
    """Return the pinned commit for *repo_id*, or ``None`` if it floats."""
    return PINNED_REVISIONS.get(repo_id)


def _with_pin(fn: Callable[..., Any], kwargs: dict[str, Any]) -> Any:
    """Inject ``revision=`` for a pinned repo, then call *fn*.

    An explicit ``revision`` passed by the caller always wins — the pin is a
    default, not an override.
    """
    repo_id = kwargs.get("repo_id")
    if repo_id and not kwargs.get("revision"):
        revision = revision_for(repo_id)
        if revision:
            kwargs["revision"] = revision
            log.debug("Pinned %s to %s", repo_id, revision[:12])
    return fn(**kwargs)


def pinned_hf_download(**kwargs: Any) -> Any:
    """``hf_hub_download`` with the pinned revision applied.

    Keyword-only, because the pin is looked up from ``repo_id``.
    """
    from huggingface_hub import hf_hub_download

    return _with_pin(hf_hub_download, kwargs)


def pinned_snapshot_download(**kwargs: Any) -> Any:
    """``snapshot_download`` with the pinned revision applied.

    Keyword-only, because the pin is looked up from ``repo_id``.
    """
    from huggingface_hub import snapshot_download

    return _with_pin(snapshot_download, kwargs)
