"""
PNG metadata extraction for ComfyUI image files.

Extracts prompt, seed, and workflow information from PNG chunk metadata
(tEXt, iTXt) that ComfyUI embeds in saved images.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from PIL import Image
from PIL.PngImagePlugin import PngInfo

logger = logging.getLogger(__name__)


def extract_png_metadata(path: str) -> dict:
    """
    Extract ComfyUI metadata from PNG chunks.

    Args:
        path: path to a PNG image file

    Returns:
        Dict with keys:
            - 'prompt': str (positive prompt if found)
            - 'seed': str (seed value if found)
            - 'workflow': str (full workflow JSON if found)
        All values default to empty string if not found.
    """
    result = {
        'prompt': '',
        'seed': '',
        'workflow': '',
    }

    if not path.lower().endswith('.png'):
        return result

    try:
        img = Image.open(path)
        if not hasattr(img, 'text'):
            return result

        text_data = img.text

        # ComfyUI stores workflow as 'workflow' key
        if 'workflow' in text_data:
            result['workflow'] = text_data['workflow']

        # ComfyUI stores prompt as 'prompt' key (JSON dict of all node inputs)
        if 'prompt' in text_data:
            result['prompt'] = _extract_positive_prompt(text_data['prompt'])

        # Extract seed from the prompt data
        if 'prompt' in text_data:
            result['seed'] = _extract_seed(text_data['prompt'])

    except Exception as e:
        logger.debug("[LoadLast] Failed to extract metadata from %s: %s", path, e)

    return result


def _extract_positive_prompt(prompt_json: str) -> str:
    """
    Extract the positive prompt text from ComfyUI's prompt JSON.

    ComfyUI stores all node inputs as a JSON dict. We look for
    CLIPTextEncode nodes and extract their 'text' input.
    """
    try:
        prompt_data = json.loads(prompt_json)
        if not isinstance(prompt_data, dict):
            return prompt_json

        # Look for positive prompt in common node types
        for node_id, node_data in prompt_data.items():
            if not isinstance(node_data, dict):
                continue
            class_type = node_data.get('class_type', '')
            inputs = node_data.get('inputs', {})

            # CLIPTextEncode is the standard text prompt node
            if class_type == 'CLIPTextEncode' and 'text' in inputs:
                text = inputs['text']
                if isinstance(text, str) and text.strip():
                    return text

        # If no CLIPTextEncode found, return the raw JSON
        return prompt_json

    except (json.JSONDecodeError, TypeError):
        return prompt_json


def _extract_seed(prompt_json: str) -> str:
    """
    Extract the seed value from ComfyUI's prompt JSON.

    Looks for KSampler nodes and extracts their 'seed' input.
    """
    try:
        prompt_data = json.loads(prompt_json)
        if not isinstance(prompt_data, dict):
            return ''

        # Look for seed in sampler nodes
        sampler_types = {'KSampler', 'KSamplerAdvanced', 'SamplerCustom',
                         'KSamplerSelect', 'SamplerCustomAdvanced'}

        for node_id, node_data in prompt_data.items():
            if not isinstance(node_data, dict):
                continue
            class_type = node_data.get('class_type', '')
            inputs = node_data.get('inputs', {})

            if class_type in sampler_types and 'seed' in inputs:
                seed = inputs['seed']
                if isinstance(seed, (int, float)):
                    return str(int(seed))

        return ''

    except (json.JSONDecodeError, TypeError):
        return ''


def extract_metadata_from_tensor_cache(cache_entry) -> dict:
    """
    Extract metadata from execution hook cache entry.

    Args:
        cache_entry: A CacheEntry from ImageExecutionCache

    Returns:
        Dict with 'prompt', 'seed', 'workflow' keys
    """
    meta = cache_entry.metadata if cache_entry.metadata else {}
    return {
        'prompt': meta.get('prompt', ''),
        'seed': str(meta.get('seed', '')),
        'workflow': meta.get('workflow', ''),
    }
