# coding: utf-8
"""No-LLM mode implementations, one module per mode.

Split out of nodes/nollm_modes.py, which had grown to 7,308 lines. The mode
functions never called one another, so each moved unchanged; shared imports,
the CRF/preset maps and the sam3/effects helpers live in _shared.py.

nodes/nollm_modes.py re-exports everything here, so existing call sites and
tests are unaffected.
"""

from ._shared import *  # noqa: F401,F403  (re-export helpers and maps)
from .effects_pipeline import process_effects_pipeline
from .sam3 import process_sam3_only
from .whisper import process_whisper_only
from .mmaudio import process_mmaudio_only
from .audiox_music import process_audiox_music_only
from .foundation1 import process_foundation1_only
from .fish_speech import process_fish_speech_only
from .ace_step import process_ace_step_only
from .audiox_inpaint import process_audiox_inpaint_only
from .sam_audio_separate import process_sam_audio_separate
from .lip_sync import process_lip_sync_only
from .animate_portrait import process_animate_portrait_only
from .marigold import process_marigold_only
from .sapiens2 import process_sapiens2_only
from .normalcrafter import process_normalcrafter_only
from .video_depth import process_video_depth_only
from .minimax_remover import process_minimax_remover_only
from .flux_klein import process_flux_klein_only
from .kiwi_edit import process_kiwi_edit_only
from .dreamid_omni import process_dreamid_omni_only
from .ai_upscale import process_ai_upscale_only
from .rembg import process_rembg_only
from .onion_skin import process_onion_skin_only
from .comparison import process_comparison_only
from .video_matting import process_video_matting_only
from .scail2 import process_scail2_only
from .sharp import process_sharp_only
from .svi import process_svi_only
from .wan_animate import process_wan_animate_only
from .phyfps import process_phyfps_only
