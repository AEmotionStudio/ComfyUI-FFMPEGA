"""MCP tool definitions formatted for LLM function-calling.

These definitions are passed to the LLM via the tools parameter so it can
dynamically discover and select skills for video editing pipelines.
"""


TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "list_skills",
            "description": (
                "List available video editing skills. "
                "Returns skill names, descriptions, parameters, and examples. "
                "Use this to discover what skills exist."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "description": "Optional category filter",
                        "enum": [
                            "temporal",
                            "spatial",
                            "visual",
                            "audio",
                            "encoding",
                            "outcome",
                        ],
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_skills",
            "description": (
                "Search for skills by keyword. Matches against skill names, "
                "descriptions, and tags. Use when the user asks for something "
                "specific like 'blue', 'slow motion', 'blur', etc."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query (e.g. 'blue', 'speed', 'crop')",
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_skill_details",
            "description": (
                "Get full details about a specific skill including all "
                "parameters, value ranges, defaults, and usage examples."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "skill_name": {
                        "type": "string",
                        "description": "Name of the skill to look up",
                    }
                },
                "required": ["skill_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_video",
            "description": (
                "Analyze a video file and return its metadata: resolution, "
                "duration, codec, FPS, audio info, file size, etc."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "video_path": {
                        "type": "string",
                        "description": "Absolute path to the video file",
                    }
                },
                "required": ["video_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "build_pipeline",
            "description": (
                "Build and validate an FFMPEG pipeline from a list of skills. "
                "Returns the composed ffmpeg command string and any validation "
                "errors. Use this to verify your pipeline before outputting "
                "the final JSON response."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "skills": {
                        "type": "array",
                        "description": (
                            "List of skill steps. Each item must have a "
                            "'name' (string) and optional 'params' (object)."
                        ),
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {
                                    "type": "string",
                                    "description": "Skill name",
                                },
                                "params": {
                                    "type": "object",
                                    "description": "Skill parameters",
                                },
                            },
                            "required": ["name"],
                        },
                    },
                    "input_path": {
                        "type": "string",
                        "description": "Input video path (use placeholder if unknown)",
                    },
                    "output_path": {
                        "type": "string",
                        "description": "Output video path (use placeholder if unknown)",
                    },
                },
                "required": ["skills"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "extract_frames",
            "description": (
                "Extract frames from the input video as PNG images for visual "
                "inspection. Returns absolute file paths to the extracted "
                "frame images. Use this to SEE the actual video content — "
                "colors, composition, lighting, subjects — before choosing "
                "effects or color grading. Only available when using a "
                "vision-capable model."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "start": {
                        "type": "number",
                        "description": (
                            "Start time in seconds to begin extraction "
                            "(default: 0)"
                        ),
                    },
                    "duration": {
                        "type": "number",
                        "description": (
                            "Duration in seconds to extract from "
                            "(default: 5)"
                        ),
                    },
                    "fps": {
                        "type": "number",
                        "description": (
                            "Frames per second to extract. 1 = one frame "
                            "per second (default: 1)"
                        ),
                    },
                    "max_frames": {
                        "type": "integer",
                        "description": (
                            "Maximum number of frames to extract "
                            "(default: 8, max: 16)"
                        ),
                    },
                },
            },
        },
    },
]
