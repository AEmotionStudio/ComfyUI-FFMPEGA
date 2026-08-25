"""
Shared constants and utilities for SeedVR2
Only includes constants actually used in the codebase
"""

# Version information
__version__ = "2.5.24"

import os
import warnings
import inspect
from typing import Optional

# Model folder names
SEEDVR2_FOLDER_NAME = "SEEDVR2" # Physical folder name on disk
SEEDVR2_MODEL_TYPE = "seedvr2" # Model type identifier for ComfyUI

# ComfyUI's shared DiT folder. SeedVR2 checkpoints in ComfyUI's native format
# (e.g. the int8_convrot ones) are normally downloaded here rather than into
# SEEDVR2/, so it is searched as a secondary location. Files found here are
# filtered by name, since it also holds every other diffusion model on disk.
SHARED_DIT_MODEL_TYPE = "diffusion_models"
SHARED_DIT_NAME_FILTER = "seedvr"

# Supported model file formats
SUPPORTED_MODEL_EXTENSIONS = {'.safetensors', '.gguf'}

# GGUF Quantization Constants
QK_K = 256
K_SCALE_SIZE = 12
GGUF_BLOCK_SIZE = 32
GGUF_TYPE_SIZE = 64

# Download configuration
HUGGINGFACE_BASE_URL = "https://huggingface.co/{repo}/resolve/main/{filename}"
DOWNLOAD_CHUNK_SIZE = 8192 * 1024  # 8MB chunks for hash calculation
DOWNLOAD_MAX_RETRIES = 3
DOWNLOAD_RETRY_DELAY = 2  # seconds

def get_script_directory() -> str:
    """Get the root script directory path (seedvr package root, 2 levels up from this file)"""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_base_cache_dir() -> str:
    """
    Get the default model cache directory path.
    
    Returns the path without creating the directory.
    
    Returns:
        str: Path to default cache directory
    """
    try:
        import folder_paths  # Only works if ComfyUI is available
        cache_dir = os.path.join(folder_paths.models_dir, SEEDVR2_FOLDER_NAME)
        folder_paths.add_model_folder_path(SEEDVR2_MODEL_TYPE, cache_dir)
    except:
        cache_dir = f"./models/{SEEDVR2_FOLDER_NAME}"
    
    return cache_dir


def get_seedvr2_model_paths() -> list:
    """Get the registered SEEDVR2 model paths including those from extra_model_paths.yaml (case-insensitive)"""
    try:
        import folder_paths
        # Ensure default path is registered first
        get_base_cache_dir()
        
        # Case-insensitive lookup: search through all registered folder types
        # This handles any case variation users might use in extra_model_paths.yaml
        all_paths = []
        target_lower = SEEDVR2_MODEL_TYPE.lower()
        
        # folder_paths.folder_names_and_paths is the underlying dict: {type: ([paths], extensions)}
        if hasattr(folder_paths, 'folder_names_and_paths'):
            for folder_type, (paths, _) in folder_paths.folder_names_and_paths.items():
                if folder_type.lower() == target_lower:
                    all_paths.extend(paths)
        
        # Remove duplicates while preserving order (os.path.normpath handles Windows/Linux path differences)
        seen = set()
        unique_paths = []
        for path in all_paths:
            normalized = os.path.normpath(path.lower())
            if normalized not in seen:
                seen.add(normalized)
                unique_paths.append(path)
        
        return unique_paths if unique_paths else [get_base_cache_dir()]
    except:
        return [get_base_cache_dir()]


def get_shared_dit_paths() -> list:
    """
    Get ComfyUI's diffusion_models directories, searched as a secondary location.

    SeedVR2 checkpoints in ComfyUI's native format land here rather than in
    SEEDVR2/. Returns an empty list when ComfyUI is unavailable or the folder
    type is not registered.
    """
    try:
        import folder_paths
        return list(folder_paths.get_folder_paths(SHARED_DIT_MODEL_TYPE))
    except:
        return []


def get_all_model_paths() -> list:
    """Get every directory searched for SeedVR2 models, in priority order.

    The dedicated SEEDVR2 folders come first, then ComfyUI's shared
    diffusion_models folders.
    """
    paths = get_seedvr2_model_paths()
    seen = {os.path.normpath(p.lower()) for p in paths}

    for path in get_shared_dit_paths():
        normalized = os.path.normpath(path.lower())
        if normalized not in seen:
            seen.add(normalized)
            paths.append(path)

    return paths


def get_all_model_files() -> dict:
    """
    Get a mapping of all model files to their full paths across all registered directories.

    Returns:
        dict: Mapping of filename -> full path for all discovered model files
    """
    model_files = {}

    # Dedicated SeedVR2 folders: everything in them is a SeedVR2 model.
    # Shared diffusion_models folders: filter by name, since they also hold
    # every unrelated Wan/Flux/etc. checkpoint on disk.
    searches = [(path, None) for path in get_seedvr2_model_paths()]
    searches += [(path, SHARED_DIT_NAME_FILTER) for path in get_shared_dit_paths()]

    for path, name_filter in searches:
        if not os.path.exists(path):
            continue
        for file in os.listdir(path):
            if not is_supported_model_file(file):
                continue
            if name_filter is not None and name_filter not in file.lower():
                continue
            # Only keep first occurrence of each file (priority order)
            if file not in model_files:
                model_files[file] = os.path.join(path, file)

    return model_files


def find_model_file(filename: str, fallback_dir: Optional[str] = None) -> str:
    """
    Find a model file in any registered path.
    
    Args:
        filename: Name of the model file to find
        fallback_dir: Directory to use if file not found in any registered path
        
    Returns:
        str: Full path to the model file
    """
    # Get all model files
    model_files = get_all_model_files()
    
    # Return path if found
    if filename in model_files:
        return model_files[filename]
    
    # Fallback to specified directory or base cache dir
    if fallback_dir:
        return os.path.join(fallback_dir, filename)
    else:
        return os.path.join(get_base_cache_dir(), filename)


def get_validation_cache_path(cache_dir: Optional[str] = None) -> str:
    """
    Get path to model validation cache file.
    
    Args:
        cache_dir: Optional directory for cache file. If None, uses default base cache dir.
        
    Returns:
        Full path to validation cache JSON file
    """
    if cache_dir is None:
        cache_dir = get_base_cache_dir()
    return os.path.join(cache_dir, ".validation_cache.json")


def is_supported_model_file(filename: str) -> bool:
    """Check if a file has a supported model extension"""
    return any(filename.endswith(ext) for ext in SUPPORTED_MODEL_EXTENSIONS)


def suppress_tensor_warnings() -> None:
    """
    Suppress common tensor conversion and numpy array warnings that are expected behavior
    when working with GGUF tensors and numpy arrays.
    """
    warnings.filterwarnings("ignore", message="To copy construct from a tensor", category=UserWarning)
    warnings.filterwarnings("ignore", message="The given NumPy array is not writable", category=UserWarning)