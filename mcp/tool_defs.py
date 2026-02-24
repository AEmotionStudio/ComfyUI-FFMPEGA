"""MCP tool definitions formatted for LLM function-calling.

These definitions are passed to the LLM via the tools parameter so it can
dynamically discover and select skills for video editing pipelines.

Each tool includes:
- Detailed parameter descriptions
- Return format documentation (helps PTC scripts parse results)
- Input examples (improves parameter accuracy per Anthropic best practices)
"""


TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "list_skills",
            "description": (
                "List available video editing skills. "
                "Returns skill names, descriptions, parameters, and examples. "
                "Use this to discover what skills exist. "
                "Returns: {total_count: int, skills: [{name: str, category: str, "
                "description: str, parameters: [{name, type, description, "
                "required, default}], tags: [str], examples: [str]}], "
                "by_category: {category: [skills]}}"
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
            "input_examples": [
                {},
                {"category": "visual"},
                {"category": "temporal"},
            ],
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_skills",
            "description": (
                "Search for skills by keyword. Matches against skill names, "
                "descriptions, and tags. Use when the user asks for something "
                "specific like 'blue', 'slow motion', 'blur', etc. "
                "Returns: {query: str, match_count: int, matches: [{name: str, "
                "category: str, description: str, tags: [str]}]}"
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
            "input_examples": [
                {"query": "color correction"},
                {"query": "slow motion"},
                {"query": "film grain vintage"},
                {"query": "fade transition"},
                {"query": "letterbox cinematic"},
            ],
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_skill_details",
            "description": (
                "Get full details about a specific skill including all "
                "parameters, value ranges, defaults, and usage examples. "
                "ALWAYS call this before using a skill in your pipeline "
                "to ensure correct parameter names and valid values. "
                "Returns: {name: str, category: str, description: str, "
                "parameters: [{name: str, type: str, description: str, "
                "required: bool, default: any, min_value: number|null, "
                "max_value: number|null, choices: [str]|null}], "
                "ffmpeg_template: str, pipeline: [str]|null, "
                "examples: [str], tags: [str]} "
                "or {error: str} if skill not found"
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
            "input_examples": [
                {"skill_name": "colorbalance"},
                {"skill_name": "film_grain"},
                {"skill_name": "letterbox"},
                {"skill_name": "fade_to_black"},
                {"skill_name": "speed"},
            ],
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_video",
            "description": (
                "Analyze a video file and return its metadata: resolution, "
                "duration, codec, FPS, audio info, file size, etc. "
                "Returns: {file_path: str, file_size_mb: float, "
                "format: str, duration_seconds: float, "
                "video: {width: int, height: int, codec: str, fps: float, "
                "pixel_format: str}, "
                "audio: {codec: str, sample_rate: int, channels: int}, "
                "analysis_text: str}"
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
            "input_examples": [
                {"video_path": "/tmp/input.mp4"},
            ],
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
                "the final JSON response. "
                "On success returns: {success: true, command: str, "
                "command_args: [str], explanation: str, step_count: int}. "
                "On failure returns: {success: false, errors: [str]}"
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
            "input_examples": [
                {
                    "skills": [
                        {"name": "colorbalance", "params": {"rs": 0.05, "gs": 0.0, "bs": -0.03}},
                        {"name": "film_grain", "params": {"intensity": "medium"}},
                    ],
                    "input_path": "/tmp/input.mp4",
                    "output_path": "/tmp/output.mp4",
                },
                {
                    "skills": [
                        {"name": "speed", "params": {"factor": 0.5}},
                        {"name": "fade_to_black", "params": {"in_duration": 1.0, "out_duration": 1.0}},
                    ],
                },
                {
                    "skills": [
                        {"name": "letterbox", "params": {"ratio": "2.35:1"}},
                    ],
                },
            ],
        },
    },
    {
        "type": "function",
        "function": {
            "name": "extract_frames",
            "description": (
                "Extract frames from the input video as PNG images for visual "
                "inspection. For vision-capable models (API and CLI), the "
                "frames will be viewable as images. Use this to SEE the actual "
                "video content — colors, composition, lighting, subjects — "
                "before choosing effects or color grading. "
                "Returns: {frame_count: int, paths: [str], folder: str}"
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
            "input_examples": [
                {"max_frames": 3},
                {"start": 0, "duration": 10, "fps": 0.5, "max_frames": 5},
                {},
            ],
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_colors",
            "description": (
                "Analyze the video's color characteristics using ffprobe "
                "signalstats. Returns numeric luminance, saturation, and "
                "color balance data with actionable recommendations. "
                "Use this for precise color metrics or as a fallback when "
                "vision is unavailable. Great for color grading decisions. "
                "Returns: {analysis_type: 'signalstats', "
                "frames_analyzed: int, "
                "luminance: {min: float, max: float, average: float, "
                "assessment: str}, "
                "saturation: {min: float, max: float, average: float, "
                "assessment: str}, "
                "color_balance: {u_average: float, v_average: float, "
                "dominant_tone: str}, "
                "hue_average: float, "
                "recommendations: [str], hint: str}"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "start": {
                        "type": "number",
                        "description": (
                            "Start time in seconds to begin analysis "
                            "(default: 0)"
                        ),
                    },
                    "duration": {
                        "type": "number",
                        "description": (
                            "Duration in seconds to analyze "
                            "(default: 5)"
                        ),
                    },
                },
            },
            "input_examples": [
                {},
                {"start": 2, "duration": 3},
            ],
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_luts",
            "description": (
                "List all available LUT (.cube / .3dl) files that can be "
                "used with the lut_apply skill. Returns each LUT's name "
                "and filename. Users can add their own LUTs by dropping "
                "files into the luts/ folder. Call this before using "
                "lut_apply to discover available looks. "
                "Returns: {luts: [{name: str, display_name: str, "
                "filename: str}], count: int, luts_folder: str, "
                "usage_hint: str}"
            ),
            "parameters": {
                "type": "object",
                "properties": {},
            },
            "input_examples": [
                {},
            ],
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_audio",
            "description": (
                "Analyze the audio characteristics of a video/audio file. "
                "Returns numeric volume (dB), EBU R128 loudness (LUFS), "
                "silence detection, and actionable recommendations. "
                "Use this before applying audio effects or to verify "
                "audio output quality. "
                "Returns: {has_audio: bool, codec: str, sample_rate: int, "
                "channels: int, channel_layout: str, "
                "volume: {mean_db: float, peak_db: float, "
                "dynamic_range_db: float, assessment: str}, "
                "loudness: {integrated_lufs: float, range_lu: float, "
                "true_peak_dbtp: float, assessment: str}, "
                "silence: {silent_sections: int, assessment: str}, "
                "recommendations: [str], hint: str}"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "start": {
                        "type": "number",
                        "description": (
                            "Start time in seconds to begin analysis "
                            "(default: 0)"
                        ),
                    },
                    "duration": {
                        "type": "number",
                        "description": (
                            "Duration in seconds to analyze "
                            "(default: 10)"
                        ),
                    },
                },
            },
            "input_examples": [
                {},
                {"start": 0, "duration": 5},
            ],
        },
    },
    {
        "type": "function",
        "function": {
            "name": "execute_code",
            "description": (
                "Execute a Python script that orchestrates multiple tool calls "
                "in a single pass. The script runs in a sandboxed environment "
                "where all tool functions are available as top-level callables: "
                "search_skills(query), get_skill_details(skill_name), "
                "list_skills(category=None), "
                "build_pipeline(skills, input_path, output_path), "
                "analyze_video(video_path), "
                "extract_frames(video_path, start, duration, fps, max_frames), "
                "analyze_colors(video_path, start, duration), "
                "list_luts(), analyze_audio(video_path, start, duration). "
                "The json module is available for serialization. "
                "Use print() to output results — ONLY print output is returned. "
                "No imports are allowed. Use this for complex requests that need "
                "multiple tool calls and data processing (search → details → build). "
                "Frames from extract_frames will be embedded as images automatically."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": (
                            "Python code to execute. Available functions: "
                            "search_skills(query), get_skill_details(skill_name), "
                            "list_skills(category=None), "
                            "build_pipeline(skills, input_path, output_path), "
                            "analyze_video(video_path), "
                            "extract_frames(video_path, start=0, duration=5, fps=1, max_frames=8), "
                            "analyze_colors(video_path, start=0.0, duration=5.0), "
                            "list_luts(), "
                            "analyze_audio(video_path, start=0.0, duration=10.0). "
                            "Use json.dumps() for JSON output. Use print() to "
                            "return results. No imports allowed."
                        ),
                    },
                },
                "required": ["code"],
            },
            "input_examples": [
                {
                    "code": (
                        "# Search for relevant skills and get details\n"
                        "results = search_skills('color correction')\n"
                        "skill = results['matches'][0]\n"
                        "details = get_skill_details(skill['name'])\n"
                        "print(json.dumps(details, indent=2))"
                    ),
                },
                {
                    "code": (
                        "# Full pipeline: search, detail, build, output\n"
                        "matches = search_skills('film grain vintage')['matches']\n"
                        "grain_skill = matches[0]['name']\n"
                        "details = get_skill_details(grain_skill)\n"
                        "result = build_pipeline(\n"
                        "    [{'name': grain_skill, 'params': {'intensity': 'medium'}}],\n"
                        "    '/tmp/input.mp4', '/tmp/output.mp4'\n"
                        ")\n"
                        "print(json.dumps(result, indent=2))"
                    ),
                },
            ],
        },
    },
]


# Keys that are safe in OpenAI-compatible function-calling schemas
_STANDARD_FUNCTION_KEYS = {"name", "description", "parameters"}


def strip_nonstandard_fields(tools: list[dict]) -> list[dict]:
    """Return tool definitions with non-standard keys removed.

    OpenAI-compatible APIs validate tool schemas strictly and may reject
    unknown fields like ``input_examples``.  This strips any keys from
    the ``function`` block that are not part of the standard spec.

    CLI connectors that embed tools as text in the prompt should use
    the raw ``TOOL_DEFINITIONS`` (with examples) instead.

    Args:
        tools: List of tool definitions (OpenAI format).

    Returns:
        Fully independent list with only standard keys in each
        ``function``.  Nested objects (e.g. ``parameters``) are
        deep-copied so mutations cannot affect the global definitions.
    """
    import copy

    cleaned = []
    for tool in tools:
        func = tool.get("function", {})
        clean_func = {}
        for k, v in func.items():
            if k in _STANDARD_FUNCTION_KEYS:
                # Deep-copy mutable nested dicts (e.g. parameters)
                clean_func[k] = copy.deepcopy(v) if isinstance(v, (dict, list)) else v
        cleaned.append({
            "type": tool.get("type", "function"),
            "function": clean_func,
        })
    return cleaned


