"""Audio feature extraction for MuseTalk using Whisper encoder.

Adapted from MuseTalk (MIT License).
Uses ``transformers.WhisperModel`` and ``AutoFeatureExtractor``
(already installed in ComfyUI).
"""

import math
from typing import List, Optional, Tuple

import librosa
import numpy as np
import torch
from einops import rearrange
from transformers import AutoFeatureExtractor, WhisperModel


class AudioProcessor:
    """Extract Whisper encoder features from audio for lip sync conditioning.

    The audio is processed through the Whisper encoder to get hidden-state
    features, which are then chunked per video frame to provide per-frame
    audio conditioning for the UNet.
    """

    def __init__(self, feature_extractor_path: str = "openai/whisper-tiny"):
        self.feature_extractor = AutoFeatureExtractor.from_pretrained(
            feature_extractor_path
        )

    def get_audio_feature(
        self,
        wav_path: str,
        weight_dtype: Optional[torch.dtype] = None,
    ) -> Tuple[List[torch.Tensor], int]:
        """Load audio and extract mel-spectrogram features.

        Args:
            wav_path: Path to audio file (any format librosa supports).
            weight_dtype: Optional dtype to cast features to.

        Returns:
            Tuple of (list of feature tensors per 30s segment, total samples).
        """
        audio, sr = librosa.load(wav_path, sr=16000)
        assert sr == 16000

        # Split into 30-second segments (Whisper's max context)
        segment_length = 30 * sr
        segments = [
            audio[i : i + segment_length]
            for i in range(0, len(audio), segment_length)
        ]

        features = []
        for segment in segments:
            feature = self.feature_extractor(
                segment,
                return_tensors="pt",
                sampling_rate=sr,
            ).input_features
            if weight_dtype is not None:
                feature = feature.to(dtype=weight_dtype)
            features.append(feature)

        return features, len(audio)

    def get_whisper_chunks(
        self,
        whisper_input_features: List[torch.Tensor],
        device: torch.device,
        weight_dtype: torch.dtype,
        whisper: WhisperModel,
        librosa_length: int,
        fps: int = 25,
        audio_padding_length_left: int = 2,
        audio_padding_length_right: int = 2,
    ) -> torch.Tensor:
        """Process audio features through Whisper encoder and chunk per frame.

        Args:
            whisper_input_features: Mel features from ``get_audio_feature``.
            device: Torch device.
            weight_dtype: Model dtype (e.g. float16).
            whisper: Loaded ``WhisperModel`` instance.
            librosa_length: Total audio samples count.
            fps: Video frame rate.
            audio_padding_length_left: Left context frames for audio.
            audio_padding_length_right: Right context frames for audio.

        Returns:
            Tensor of shape ``[num_frames, seq_len, 384]`` — per-frame
            audio conditioning features.
        """
        feature_length_per_frame = 2 * (
            audio_padding_length_left + audio_padding_length_right + 1
        )

        # Encode all segments through Whisper encoder
        whisper_features = []
        for input_feature in whisper_input_features:
            input_feature = input_feature.to(device).to(weight_dtype)
            hidden_states = whisper.encoder(
                input_feature, output_hidden_states=True
            ).hidden_states
            stacked = torch.stack(hidden_states, dim=2)
            whisper_features.append(stacked)

        whisper_feature = torch.cat(whisper_features, dim=1)

        # Trim to actual audio length
        sr = 16000
        audio_fps = 50  # Whisper operates at 50 features/sec
        fps = int(fps)
        whisper_idx_multiplier = audio_fps / fps
        num_frames = math.floor((librosa_length / sr) * fps)
        actual_length = math.floor((librosa_length / sr) * audio_fps)
        whisper_feature = whisper_feature[:, :actual_length, ...]

        # Pad start and end to avoid out-of-bounds
        padding_nums = math.ceil(whisper_idx_multiplier)
        whisper_feature = torch.cat(
            [
                torch.zeros_like(
                    whisper_feature[:, : padding_nums * audio_padding_length_left]
                ),
                whisper_feature,
                torch.zeros_like(
                    whisper_feature[
                        :, : padding_nums * 3 * audio_padding_length_right
                    ]
                ),
            ],
            dim=1,
        )

        # Chunk features per video frame
        audio_prompts = []
        for frame_idx in range(num_frames):
            audio_idx = math.floor(frame_idx * whisper_idx_multiplier)
            clip = whisper_feature[
                :, audio_idx : audio_idx + feature_length_per_frame
            ]
            if clip.shape[1] < feature_length_per_frame:
                # Pad if we're at the end
                pad = torch.zeros_like(
                    whisper_feature[
                        :, : feature_length_per_frame - clip.shape[1]
                    ]
                )
                clip = torch.cat([clip, pad], dim=1)
            audio_prompts.append(clip)

        audio_prompts = torch.cat(audio_prompts, dim=0)  # [T, len, layers, 384]
        audio_prompts = rearrange(audio_prompts, "b c h w -> b (c h) w")
        return audio_prompts
