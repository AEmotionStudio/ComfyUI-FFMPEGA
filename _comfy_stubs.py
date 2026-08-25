"""Shared ComfyUI stubs for running the test suite outside ComfyUI.

Both the root conftest.py and tests/conftest.py install a fake ``folder_paths``
module; this keeps the model-folder half of that fake in one place so the two
cannot drift.

Lives at the project root rather than under tests/ because an unrelated ``tests``
package in site-packages shadows the local one.
"""

import os

# Mirrors ComfyUI's real layout closely enough for the model-discovery code to
# exercise its normal branches instead of falling into its except: fallbacks.
MOCK_MODELS_DIR = "/tmp/comfyui_models"

# ComfyUI resolves "diffusion_models" to both models/unet and
# models/diffusion_models, which is why that key lists two directories.
_MOCK_FOLDERS = {
    "diffusion_models": ["unet", "diffusion_models"],
    "unet": ["unet"],
    "checkpoints": ["checkpoints"],
    "vae": ["vae"],
    "loras": ["loras"],
    "clip": ["clip"],
    "text_encoders": ["text_encoders"],
    "upscale_models": ["upscale_models"],
}

_SUPPORTED_EXTENSIONS = {".safetensors", ".gguf", ".sft", ".pt", ".pth", ".ckpt"}


def install_model_folders(module):
    """Add ComfyUI's model-folder API to a stub ``folder_paths`` module.

    ``get_folder_paths`` returns [] for folder names the stub does not know,
    where real ComfyUI raises KeyError. Deliberate: a stub that throws on every
    unlisted folder name turns any new model-folder reference in the codebase
    into an unrelated test failure.
    """
    module.models_dir = MOCK_MODELS_DIR
    module.folder_names_and_paths = {
        name: ([os.path.join(MOCK_MODELS_DIR, sub) for sub in subs],
               set(_SUPPORTED_EXTENSIONS))
        for name, subs in _MOCK_FOLDERS.items()
    }

    def get_folder_paths(folder_name):
        entry = module.folder_names_and_paths.get(folder_name)
        return list(entry[0]) if entry else []

    def add_model_folder_path(folder_name, full_folder_path, is_default=False):
        entry = module.folder_names_and_paths.setdefault(
            folder_name, ([], set(_SUPPORTED_EXTENSIONS))
        )
        if full_folder_path not in entry[0]:
            if is_default:
                entry[0].insert(0, full_folder_path)
            else:
                entry[0].append(full_folder_path)

    module.get_folder_paths = get_folder_paths
    module.add_model_folder_path = add_model_folder_path
    return module
