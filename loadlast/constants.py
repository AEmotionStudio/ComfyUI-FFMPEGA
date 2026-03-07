"""Shared constants for the LoadLast module."""

# Default max frames to decode (prevents OOM on long videos).
# Used by both LoadLastVideo (as the user-facing default) and
# VideoDecoder (as the fallback cap when frame count is indeterminate).
DEFAULT_MAX_FRAMES = 128
