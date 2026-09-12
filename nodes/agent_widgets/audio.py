# coding: utf-8
"""Audio generation, separation and output widgets.

Extracted verbatim from FFMPEGAgentNode.INPUT_TYPES. The text is preserved
exactly because ComfyUI restores saved workflows by widget *position* — see
tests/test_widget_order.py, which pins the emitted order.

Each function is called once per INPUT_TYPES() call, so dropdowns that read
the filesystem (LoRA lists, expression presets) stay dynamic.
"""

from __future__ import annotations



def sam_audio() -> dict:
    """Advanced: SAM-Audio."""
    return {
        "sam_audio_model": (["base", "base-fp8", "large-fp8", "large"], {
            "default": "base",
            "tooltip": "SAM-Audio model variant for audio_separate mode. "
                       "'base' = 3.6 GiB BF16 (default). "
                       "'base-fp8' = 1.8 GiB FP8 scaled (half VRAM, ~same quality). "
                       "'large-fp8' = 3.5 GiB FP8 scaled (large quality at base VRAM — recommended). "
                       "'large' = 6.9 GiB BF16 (best quality, needs 12+ GB VRAM). "
                       "Models auto-download on first use.",
        }),
    }

def output_mode() -> dict:
    """Advanced: Audio Output Mode."""
    return {
        "audio_output_mode": (["auto", "replace", "mix", "save_only"], {
            "default": "auto",
            "tooltip": "How to combine AI-generated audio with existing audio. "
                       "Applies to all audio-generating modes: generate_audio (MMAudio), generate_music (AudioX), foundation1 (Foundation-1), fish_speech (Fish Speech TTS), audio_inpaint (AudioX), audio_separate (SAM-Audio), ace_step. "
                       "'auto' lets the LLM decide in agentic mode; defaults to 'replace' in no-LLM modes. "
                       "'replace' replaces existing audio entirely. "
                       "'mix' blends generated audio with the original track. "
                       "'save_only' generates the audio file without muxing it into the video.",
        }),
    }

def resample_rate() -> dict:
    """Advanced: Audio Resample Rate."""
    return {
        "audio_resample_rate": (["off", "44100", "48000"], {
            "default": "off",
            "tooltip": "Resample the audio output to this sample rate. "
                       "Enable this if your audio effects (e.g. clean_audio with loudnorm) "
                       "produce non-standard sample rates (like 96kHz) that ComfyUI's "
                       "Save Audio MP3 node can't handle. "
                       "'off' = pass through original sample rate. "
                       "'44100' = CD quality, universal MP3 compatibility. "
                       "'48000' = studio quality, universal compatibility.",
        }),
    }

def foundation1() -> dict:
    """Advanced: Foundation-1 controls."""
    return {
        "f1_preset": (["none", "warm_pad", "synth_lead", "bass_loop", "string_ensemble", "electric_piano", "plucked_arp", "ambient_texture", "brass_stab", "guitar_clean", "mallet_vibes"], {
            "default": "none",
            "tooltip": "Built-in timbre preset for Foundation-1. "
                       "Provides structured instrument/timbre tags. "
                       "Combine with a text prompt for customization. "
                       "Only used when no_llm_mode = 'foundation1'.",
        }),
        "f1_instrument": (["none", "synth", "keys", "bass", "strings", "mallet", "winds", "guitar", "brass", "vocals", "plucked"], {
            "default": "none",
            "tooltip": "Instrument family to guide Foundation-1 generation. "
                       "Appended to prompt automatically. 'none' = let the prompt decide. "
                       "Only used when no_llm_mode = 'foundation1'.",
        }),
        "f1_fx": (["none", "dry", "low_reverb", "medium_reverb", "high_reverb", "plate_reverb", "low_delay", "medium_delay", "ping_pong_delay", "stereo_delay", "low_distortion", "medium_distortion", "phaser", "bitcrush", "chorus"], {
            "default": "none",
            "tooltip": "FX processing applied to Foundation-1 output. "
                       "'dry' = minimal processing, other options add specific effects. "
                       "Only used when no_llm_mode = 'foundation1'.",
        }),
        "f1_structure": (["none", "chord_progression", "melody", "arp", "sustained", "staccato", "legato", "triplets", "rhythmic", "rising", "falling", "simple", "complex"], {
            "default": "none",
            "tooltip": "Musical structure/notation tag to guide phrasing. "
                       "Controls melodic motion, rhythmic behavior, and harmonic feel. "
                       "Only used when no_llm_mode = 'foundation1'.",
        }),
        "f1_negative_prompt": ("STRING", {
            "default": "",
            "multiline": True,
            "placeholder": "e.g. harsh, distorted, noise",
            "tooltip": "Negative prompt describing what to avoid in Foundation-1 output. "
                       "Only used when no_llm_mode = 'foundation1'.",
        }),
        "f1_bpm": (["auto", "100", "110", "120", "128", "130", "140", "150"], {
            "default": "auto",
            "tooltip": "Target BPM. Foundation-1 supports specific BPM denominations. "
                       "'auto' = let the model decide. "
                       "Only used when no_llm_mode = 'foundation1'.",
        }),
        "f1_bars": (["auto", "4", "8"], {
            "default": "auto",
            "tooltip": "Number of bars for the loop. Foundation-1 supports 4 or 8 bars. "
                       "'auto' = let the model decide. Combined with BPM for precise duration. "
                       "Only used when no_llm_mode = 'foundation1'.",
        }),
        "f1_key": ("STRING", {
            "default": "",
            "multiline": False,
            "placeholder": "e.g. C major, A minor, F# dorian",
            "tooltip": "Musical key and mode. Supports all keys and modes. "
                       "Leave empty for automatic. "
                       "Only used when no_llm_mode = 'foundation1'.",
        }),
        "f1_duration": ("FLOAT", {
            "default": 0.0,
            "min": 0.0,
            "max": 60.0,
            "step": 0.5,
            "tooltip": "Duration in seconds. 0 = auto-calculate from BPM/bars (or default 10s). "
                       "Max 60s. Only used when no_llm_mode = 'foundation1'.",
        }),
        "f1_steps": ("INT", {
            "default": 100,
            "min": 10,
            "max": 250,
            "step": 10,
            "tooltip": "Number of diffusion steps. Higher = better quality but slower. "
                       "100 is a good default. Only used when no_llm_mode = 'foundation1'.",
        }),
        "f1_cfg_scale": ("FLOAT", {
            "default": 7.0,
            "min": 1.0,
            "max": 15.0,
            "step": 0.5,
            "tooltip": "Classifier-free guidance scale. Higher = follows prompt more closely. "
                       "7.0 is a good default. Only used when no_llm_mode = 'foundation1'.",
        }),
        "f1_style_transfer": ("BOOLEAN", {
            "default": False,
            "tooltip": "Enable audio style transfer mode. "
                       "When on, Foundation-1 takes connected audio_a input and re-styles it "
                       "based on the text prompt — like img2img but for audio. "
                       "Requires audio_a to be connected. "
                       "Only used when no_llm_mode = 'foundation1'.",
        }),
        "f1_noise_level": ("FLOAT", {
            "default": 0.7,
            "min": 0.0,
            "max": 1.0,
            "step": 0.05,
            "tooltip": "Style transfer strength. "
                       "0.0 = keep original audio (no change), "
                       "0.3 = subtle variation, "
                       "0.7 = strong restyling (default), "
                       "1.0 = fully regenerate (ignore source). "
                       "Only used when f1_style_transfer is enabled.",
        }),
    }

def fish_speech() -> dict:
    """Advanced: Fish Speech TTS controls."""
    return {
        "fish_model_variant": (["bf16", "fp8"], {
            "default": "bf16",
            "tooltip": "Fish Speech model precision. "
                       "'fp8' = FP8 quantized (~12 GB VRAM, recommended). "
                       "'bf16' = full BF16 precision (~24 GB VRAM). "
                       "Only used when no_llm_mode = 'fish_speech'.",
        }),
        "fish_voice": ("STRING", {
            "default": "",
            "multiline": False,
            "placeholder": "Voice name or path to .wav reference",
            "tooltip": "Voice reference for cloning. Enter a name from the voice library "
                       "(models/fish_speech/voices/) or a path to a .wav file (10-30s). "
                       "Leave empty for default voice. "
                       "Only used when no_llm_mode = 'fish_speech'.",
        }),
        "fish_emotion": (["(none)", "[happy]", "[sad]", "[angry]", "[excited]", "[whisper]", "[shouting]", "[laughing]", "[laughing tone]", "[chuckling]", "[chuckle]", "[crying]", "[singing]", "[pause]", "[short pause]", "[breath]", "[inhale]", "[exhale]", "[emphasis]", "[sigh]", "[tsk]", "[nervous]", "[calm]", "[serious]", "[cheerful]", "[sarcastic]", "[surprised]", "[shocked]", "[disgusted]", "[fearful]", "[tender]", "[delight]", "[monotone]", "[interrupting]", "[fast]", "[slow]", "[loud]", "[soft]", "[low voice]", "[volume up]", "[volume down]", "[echo]", "[panting]", "[clearing throat]", "[audience laughter]", "[with strong accent]"], {
            "default": "(none)",
            "tooltip": "Emotion/prosody tag prepended to the text. "
                       "Fish Speech supports 15K+ inline tags — including free-form "
                       "descriptions like '[whisper in small voice]' or "
                       "'[professional broadcast tone]'. Type tags directly in the prompt "
                       "for fine-grained control. Only used when no_llm_mode = 'fish_speech'.",
        }),
        "fish_temperature": ("FLOAT", {
            "default": 0.8,
            "min": 0.1,
            "max": 1.0,
            "step": 0.05,
            "tooltip": "Sampling temperature for Fish Speech. "
                       "Lower = more deterministic, higher = more varied. "
                       "Only used when no_llm_mode = 'fish_speech'.",
        }),
        "fish_top_p": ("FLOAT", {
            "default": 0.8,
            "min": 0.1,
            "max": 1.0,
            "step": 0.05,
            "tooltip": "Top-p (nucleus) sampling for Fish Speech. "
                       "Only used when no_llm_mode = 'fish_speech'.",
        }),
        "fish_repetition_penalty": ("FLOAT", {
            "default": 1.1,
            "min": 1.0,
            "max": 2.0,
            "step": 0.05,
            "tooltip": "Repetition penalty for Fish Speech. "
                       "Higher values reduce repetitive patterns. "
                       "Only used when no_llm_mode = 'fish_speech'.",
        }),
    }
