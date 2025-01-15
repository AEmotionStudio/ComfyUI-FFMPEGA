"""FFMPEG command reference database."""

FFMPEG_COMMAND_REFERENCE = {
    "global_options": {
        "-y": {
            "description": "Overwrite output files without asking",
            "example": "ffmpeg -y -i input.mp4 output.mp4",
        },
        "-n": {
            "description": "Do not overwrite output files",
            "example": "ffmpeg -n -i input.mp4 output.mp4",
        },
        "-v": {
            "description": "Set logging verbosity level",
            "values": ["quiet", "panic", "fatal", "error", "warning", "info", "verbose", "debug"],
            "example": "ffmpeg -v error -i input.mp4 output.mp4",
        },
        "-hide_banner": {
            "description": "Hide FFMPEG banner and version info",
            "example": "ffmpeg -hide_banner -i input.mp4 output.mp4",
        },
    },
    "input_options": {
        "-i": {
            "description": "Input file path",
            "example": "ffmpeg -i input.mp4 output.mp4",
        },
        "-ss": {
            "description": "Seek to position (as input option, fast seeking)",
            "format": "HH:MM:SS.mmm or seconds",
            "example": "ffmpeg -ss 00:01:30 -i input.mp4 output.mp4",
        },
        "-t": {
            "description": "Limit input duration",
            "format": "seconds or HH:MM:SS",
            "example": "ffmpeg -i input.mp4 -t 60 output.mp4",
        },
        "-to": {
            "description": "Stop reading at position",
            "format": "HH:MM:SS.mmm or seconds",
            "example": "ffmpeg -i input.mp4 -to 00:02:00 output.mp4",
        },
        "-loop": {
            "description": "Loop input (for images/GIFs)",
            "example": "ffmpeg -loop 1 -i image.png -t 10 output.mp4",
        },
    },
    "output_options": {
        "-c:v": {
            "description": "Video codec",
            "values": ["libx264", "libx265", "libvpx-vp9", "libaom-av1", "copy"],
            "example": "ffmpeg -i input.mp4 -c:v libx264 output.mp4",
        },
        "-c:a": {
            "description": "Audio codec",
            "values": ["aac", "libmp3lame", "libopus", "flac", "copy"],
            "example": "ffmpeg -i input.mp4 -c:a aac output.mp4",
        },
        "-crf": {
            "description": "Constant Rate Factor (quality, lower=better)",
            "range": "0-51 for H.264 (23 default)",
            "example": "ffmpeg -i input.mp4 -c:v libx264 -crf 18 output.mp4",
        },
        "-preset": {
            "description": "Encoding speed preset",
            "values": ["ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow"],
            "example": "ffmpeg -i input.mp4 -c:v libx264 -preset slow output.mp4",
        },
        "-b:v": {
            "description": "Video bitrate",
            "format": "number with k/M suffix",
            "example": "ffmpeg -i input.mp4 -b:v 5M output.mp4",
        },
        "-b:a": {
            "description": "Audio bitrate",
            "format": "number with k suffix",
            "example": "ffmpeg -i input.mp4 -b:a 192k output.mp4",
        },
        "-r": {
            "description": "Output frame rate",
            "example": "ffmpeg -i input.mp4 -r 30 output.mp4",
        },
        "-s": {
            "description": "Output resolution",
            "format": "WxH",
            "example": "ffmpeg -i input.mp4 -s 1920x1080 output.mp4",
        },
        "-aspect": {
            "description": "Set aspect ratio",
            "format": "W:H or decimal",
            "example": "ffmpeg -i input.mp4 -aspect 16:9 output.mp4",
        },
        "-an": {
            "description": "Disable audio",
            "example": "ffmpeg -i input.mp4 -an output.mp4",
        },
        "-vn": {
            "description": "Disable video",
            "example": "ffmpeg -i input.mp4 -vn output.mp3",
        },
        "-f": {
            "description": "Force output format",
            "values": ["mp4", "webm", "mkv", "mov", "gif", "null"],
            "example": "ffmpeg -i input.mp4 -f webm output.webm",
        },
        "-movflags": {
            "description": "MOV/MP4 muxer flags",
            "values": ["+faststart", "+frag_keyframe"],
            "example": "ffmpeg -i input.mp4 -movflags +faststart output.mp4",
        },
        "-pix_fmt": {
            "description": "Pixel format",
            "values": ["yuv420p", "yuv422p", "yuv444p", "rgb24"],
            "example": "ffmpeg -i input.mp4 -pix_fmt yuv420p output.mp4",
        },
    },
    "filter_options": {
        "-vf": {
            "description": "Video filter graph (simple)",
            "example": "ffmpeg -i input.mp4 -vf 'scale=1280:720' output.mp4",
        },
        "-af": {
            "description": "Audio filter graph (simple)",
            "example": "ffmpeg -i input.mp4 -af 'volume=2.0' output.mp4",
        },
        "-filter_complex": {
            "description": "Complex filter graph (multiple inputs/outputs)",
            "example": "ffmpeg -i v1.mp4 -i v2.mp4 -filter_complex '[0:v][1:v]hstack' output.mp4",
        },
    },
    "hardware_acceleration": {
        "-hwaccel": {
            "description": "Hardware acceleration method",
            "values": ["auto", "cuda", "vaapi", "qsv", "videotoolbox"],
            "example": "ffmpeg -hwaccel cuda -i input.mp4 output.mp4",
        },
        "-hwaccel_device": {
            "description": "Hardware acceleration device",
            "example": "ffmpeg -hwaccel cuda -hwaccel_device 0 -i input.mp4 output.mp4",
        },
    },
    "common_recipes": {
        "resize_720p": {
            "description": "Resize video to 720p",
            "command": "ffmpeg -i input.mp4 -vf 'scale=-1:720' output.mp4",
        },
        "trim_segment": {
            "description": "Extract segment from 1:00 to 2:00",
            "command": "ffmpeg -ss 00:01:00 -i input.mp4 -to 00:01:00 -c copy output.mp4",
        },
        "compress_web": {
            "description": "Compress for web delivery",
            "command": "ffmpeg -i input.mp4 -c:v libx264 -crf 23 -preset medium -c:a aac -b:a 128k -movflags +faststart output.mp4",
        },
        "extract_audio": {
            "description": "Extract audio as MP3",
            "command": "ffmpeg -i input.mp4 -vn -c:a libmp3lame -b:a 192k output.mp3",
        },
        "gif_conversion": {
            "description": "Convert video to GIF",
            "command": "ffmpeg -i input.mp4 -vf 'fps=10,scale=320:-1:flags=lanczos' -c:v gif output.gif",
        },
        "concat_videos": {
            "description": "Concatenate multiple videos",
            "command": "ffmpeg -f concat -safe 0 -i filelist.txt -c copy output.mp4",
        },
        "add_watermark": {
            "description": "Add image watermark",
            "command": "ffmpeg -i input.mp4 -i logo.png -filter_complex 'overlay=W-w-10:H-h-10' output.mp4",
        },
        "stabilize": {
            "description": "Stabilize shaky video (two-pass)",
            "commands": [
                "ffmpeg -i input.mp4 -vf vidstabdetect -f null -",
                "ffmpeg -i input.mp4 -vf vidstabtransform output.mp4",
            ],
        },
    },
}
