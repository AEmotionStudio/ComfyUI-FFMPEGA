"""FFMPEG filter reference database."""

FFMPEG_FILTERS = {
    "video_filters": {
        "scale": {
            "description": "Resize video",
            "syntax": "scale=w:h",
            "parameters": {
                "w": "Output width (-1 for auto)",
                "h": "Output height (-1 for auto)",
                "force_original_aspect_ratio": "decrease, increase, or disable",
            },
            "examples": [
                "scale=1920:1080",
                "scale=-1:720",
                "scale=iw/2:ih/2",
                "scale=1280:720:force_original_aspect_ratio=decrease",
            ],
        },
        "crop": {
            "description": "Crop video region",
            "syntax": "crop=w:h:x:y",
            "parameters": {
                "w": "Output width",
                "h": "Output height",
                "x": "X position (default: center)",
                "y": "Y position (default: center)",
            },
            "examples": [
                "crop=1280:720:0:180",
                "crop=in_w:in_w*9/16",
                "crop=iw-100:ih-100:50:50",
            ],
        },
        "pad": {
            "description": "Add padding/borders",
            "syntax": "pad=w:h:x:y:color",
            "parameters": {
                "w": "Output width",
                "h": "Output height",
                "x": "Video X position",
                "y": "Video Y position",
                "color": "Padding color",
            },
            "examples": [
                "pad=1920:1080:(ow-iw)/2:(oh-ih)/2:black",
                "pad=iw:iw*9/16:(ow-iw)/2:(oh-ih)/2",
            ],
        },
        "setpts": {
            "description": "Set presentation timestamps (speed)",
            "syntax": "setpts=PTS*factor",
            "examples": [
                "setpts=0.5*PTS",  # 2x speed
                "setpts=2.0*PTS",  # 0.5x speed
                "setpts=PTS-STARTPTS",  # Reset timestamps
            ],
        },
        "fps": {
            "description": "Convert frame rate",
            "syntax": "fps=rate",
            "examples": [
                "fps=30",
                "fps=24",
                "fps=60",
            ],
        },
        "eq": {
            "description": "Adjust brightness/contrast/saturation",
            "syntax": "eq=brightness:contrast:saturation",
            "parameters": {
                "brightness": "-1.0 to 1.0 (default 0)",
                "contrast": "0 to 3.0 (default 1)",
                "saturation": "0 to 3.0 (default 1)",
                "gamma": "0.1 to 10 (default 1)",
            },
            "examples": [
                "eq=brightness=0.1:contrast=1.2",
                "eq=saturation=0",  # Grayscale
                "eq=brightness=-0.1:saturation=0.8",
            ],
        },
        "hue": {
            "description": "Adjust hue and saturation",
            "syntax": "hue=h:s",
            "parameters": {
                "h": "Hue rotation in degrees",
                "s": "Saturation multiplier",
            },
            "examples": [
                "hue=h=90",
                "hue=s=0.5",
            ],
        },
        "unsharp": {
            "description": "Sharpen or blur",
            "syntax": "unsharp=lx:ly:la:cx:cy:ca",
            "examples": [
                "unsharp=5:5:1.0:5:5:0.0",  # Sharpen
                "unsharp=5:5:-1.0:5:5:0.0",  # Blur
            ],
        },
        "boxblur": {
            "description": "Apply box blur",
            "syntax": "boxblur=luma_radius:chroma_radius",
            "examples": [
                "boxblur=5:5",
                "boxblur=10:10",
            ],
        },
        "vignette": {
            "description": "Add vignette effect",
            "syntax": "vignette=angle",
            "examples": [
                "vignette=PI/4",
                "vignette=angle=PI/4",
            ],
        },
        "fade": {
            "description": "Add fade in/out",
            "syntax": "fade=t=type:st=start:d=duration",
            "parameters": {
                "t": "in or out",
                "st": "Start time in seconds",
                "d": "Duration in seconds",
            },
            "examples": [
                "fade=t=in:st=0:d=2",
                "fade=t=out:st=8:d=2",
            ],
        },
        "transpose": {
            "description": "Rotate video",
            "syntax": "transpose=dir",
            "values": {
                "0": "90 counter-clockwise + vertical flip",
                "1": "90 clockwise",
                "2": "90 counter-clockwise",
                "3": "90 clockwise + vertical flip",
            },
            "examples": [
                "transpose=1",
                "transpose=2",
            ],
        },
        "hflip": {
            "description": "Horizontal flip",
            "syntax": "hflip",
        },
        "vflip": {
            "description": "Vertical flip",
            "syntax": "vflip",
        },
        "reverse": {
            "description": "Reverse video",
            "syntax": "reverse",
            "note": "Requires loading entire video into memory",
        },
        "loop": {
            "description": "Loop video",
            "syntax": "loop=loop:size:start",
            "examples": [
                "loop=loop=3:size=32767:start=0",
            ],
        },
        "overlay": {
            "description": "Overlay one video on another",
            "syntax": "overlay=x:y",
            "examples": [
                "overlay=W-w-10:H-h-10",  # Bottom-right corner
                "overlay=(W-w)/2:(H-h)/2",  # Center
            ],
        },
        "drawtext": {
            "description": "Draw text on video",
            "syntax": "drawtext=text:fontsize:fontcolor:x:y",
            "examples": [
                "drawtext=text='Hello':fontsize=30:fontcolor=white:x=10:y=10",
                "drawtext=text='%{pts}':fontsize=20:x=10:y=10",
            ],
        },
        "colorbalance": {
            "description": "Adjust color balance",
            "syntax": "colorbalance=rs:gs:bs:rm:gm:bm:rh:gh:bh",
            "examples": [
                "colorbalance=rs=0.1:rm=0.05",  # Warm
                "colorbalance=bs=0.1:bm=0.05",  # Cool
            ],
        },
        "curves": {
            "description": "Apply color curves",
            "syntax": "curves=preset",
            "presets": [
                "color_negative",
                "cross_process",
                "darker",
                "increase_contrast",
                "lighter",
                "linear_contrast",
                "medium_contrast",
                "negative",
                "strong_contrast",
                "vintage",
            ],
        },
        "noise": {
            "description": "Add noise/grain",
            "syntax": "noise=alls:allf",
            "examples": [
                "noise=alls=20:allf=t+u",
            ],
        },
        "hqdn3d": {
            "description": "High quality denoise",
            "syntax": "hqdn3d=luma_spatial:chroma_spatial:luma_tmp:chroma_tmp",
            "examples": [
                "hqdn3d=4:3:6:4",
            ],
        },
        "vidstabdetect": {
            "description": "Detect camera shake (pass 1)",
            "syntax": "vidstabdetect=shakiness:accuracy:stepsize:mincontrast:result",
        },
        "vidstabtransform": {
            "description": "Apply stabilization (pass 2)",
            "syntax": "vidstabtransform=smoothing:input",
        },
    },
    "audio_filters": {
        "volume": {
            "description": "Adjust volume",
            "syntax": "volume=gain",
            "examples": [
                "volume=2.0",
                "volume=0.5",
                "volume=6dB",
            ],
        },
        "atempo": {
            "description": "Adjust audio tempo (0.5-2.0)",
            "syntax": "atempo=tempo",
            "examples": [
                "atempo=2.0",
                "atempo=0.5",
            ],
            "note": "Chain multiple for values outside 0.5-2.0",
        },
        "afade": {
            "description": "Audio fade in/out",
            "syntax": "afade=t=type:st=start:d=duration",
            "examples": [
                "afade=t=in:st=0:d=2",
                "afade=t=out:st=8:d=2",
            ],
        },
        "aecho": {
            "description": "Add echo effect",
            "syntax": "aecho=in_gain:out_gain:delays:decays",
            "examples": [
                "aecho=0.8:0.9:500:0.5",
            ],
        },
        "loudnorm": {
            "description": "Normalize loudness",
            "syntax": "loudnorm=I:LRA:TP",
            "examples": [
                "loudnorm",
                "loudnorm=I=-16:LRA=11:TP=-1.5",
            ],
        },
        "bass": {
            "description": "Boost/cut bass frequencies",
            "syntax": "bass=g=gain:f=frequency",
            "examples": [
                "bass=g=6:f=100",
            ],
        },
        "treble": {
            "description": "Boost/cut treble frequencies",
            "syntax": "treble=g=gain:f=frequency",
            "examples": [
                "treble=g=4:f=3000",
            ],
        },
        "acompressor": {
            "description": "Dynamic range compression",
            "syntax": "acompressor=threshold:ratio:attack:release",
            "examples": [
                "acompressor=threshold=-20dB:ratio=4",
            ],
        },
        "areverse": {
            "description": "Reverse audio",
            "syntax": "areverse",
        },
        "aresample": {
            "description": "Resample audio",
            "syntax": "aresample=sample_rate",
            "examples": [
                "aresample=44100",
                "aresample=48000",
            ],
        },
    },
}
