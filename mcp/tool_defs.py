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
]
