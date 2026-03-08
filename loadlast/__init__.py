"""
LoadLast — Auto-discover and load recently generated images and videos.

Merged into ComfyUI-FFMPEGA. Provides LoadLastImage and LoadLastVideo nodes.
"""

# Lazy imports — these modules depend on torch which may not be available
# in lightweight test environments. The node classes are imported on-demand.

_CLASSES_LOADED = False
_LoadLastImage = None
_LoadLastVideo = None


def _load_classes():
    global _CLASSES_LOADED, _LoadLastImage, _LoadLastVideo
    if _CLASSES_LOADED:
        return
    _CLASSES_LOADED = True
    try:
        from .load_last_image import LoadLastImage as _LLI
        from .load_last_video import LoadLastVideo as _LLV
        _LoadLastImage = _LLI
        _LoadLastVideo = _LLV
    except ImportError:
        pass


def __getattr__(name):
    if name == "LoadLastImage":
        _load_classes()
        if _LoadLastImage is None:
            raise ImportError("LoadLastImage requires torch")
        return _LoadLastImage
    elif name == "LoadLastVideo":
        _load_classes()
        if _LoadLastVideo is None:
            raise ImportError("LoadLastVideo requires torch")
        return _LoadLastVideo
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["LoadLastImage", "LoadLastVideo"]
