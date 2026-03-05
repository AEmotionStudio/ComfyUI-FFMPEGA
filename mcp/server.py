"""MCP Server implementation for FFMPEGA."""

import json
from typing import Optional

from .tools import (
    analyze_video,
    list_skills,
    build_pipeline,
    execute_pipeline,
    search_skills,
    get_skill_details,
    validate_skill_params,
    extract_frames,
    cleanup_vision_frames,
    analyze_colors,
    analyze_audio,
    list_luts,
)
from .resources import get_resource


class FFMPEGAMCPServer:
    """Python-based MCP server for FFMPEG command database."""

    def __init__(self):
        """Initialize the MCP server."""
        self._tools = {
            "analyze_video": {
                "name": "analyze_video",
                "description": "Analyze input video properties and metadata",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "video_path": {
                            "type": "string",
                            "description": "Path to video file",
                        },
                        "detail": {
                            "type": "string",
                            "description": "Level of detail: 'summary' for compact output or 'full' for everything",
                            "enum": ["summary", "full"],
                        },
                    },
                    "required": ["video_path"],
                },
            },
            "list_skills": {
                "name": "list_skills",
                "description": (
                    "List available editing skills (compact index: names, categories, tags). "
                    "Use search_skills to find specific skills, then get_skill_details "
                    "before building a pipeline."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "category": {
                            "type": "string",
                            "description": "Optional category filter",
                            "enum": ["temporal", "spatial", "visual", "audio", "encoding", "outcome"],
                        }
                    },
                },
            },
            "search_skills": {
                "name": "search_skills",
                "description": "Search for skills by keyword (matches names, descriptions, tags)",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query",
                        }
                    },
                    "required": ["query"],
                },
            },
            "get_skill_details": {
                "name": "get_skill_details",
                "description": (
                    "Get full details about a specific skill including parameters, "
                    "value ranges, defaults, ffmpeg template, and examples. "
                    "Always call this before using a skill in a pipeline."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "skill_name": {
                            "type": "string",
                            "description": "Name of the skill",
                        }
                    },
                    "required": ["skill_name"],
                },
            },
            "validate_skill_params": {
                "name": "validate_skill_params",
                "description": "Validate parameters for a skill before building a pipeline",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "skill_name": {
                            "type": "string",
                            "description": "Name of the skill",
                        },
                        "params": {
                            "type": "object",
                            "description": "Parameters to validate",
                        },
                    },
                    "required": ["skill_name", "params"],
                },
            },
            "build_pipeline": {
                "name": "build_pipeline",
                "description": "Build FFMPEG command pipeline from skill list",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "skills": {
                            "type": "array",
                            "description": "List of skill specifications",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                                    "params": {"type": "object"},
                                },
                                "required": ["name"],
                            },
                        },
                        "input_path": {
                            "type": "string",
                            "description": "Input video path",
                        },
                        "output_path": {
                            "type": "string",
                            "description": "Output video path",
                        },
                    },
                    "required": ["skills", "input_path", "output_path"],
                },
            },
            "execute_pipeline": {
                "name": "execute_pipeline",
                "description": "Execute built pipeline",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "pipeline_id": {
                            "type": "string",
                            "description": "Pipeline ID to execute",
                        }
                    },
                    "required": ["pipeline_id"],
                },
            },
            "extract_frames": {
                "name": "extract_frames",
                "description": "Extract frames from a video as PNG images for visual inspection",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "video_path": {
                            "type": "string",
                            "description": "Path to video file",
                        },
                        "start": {
                            "type": "number",
                            "description": "Start time in seconds (default: 0)",
                        },
                        "duration": {
                            "type": "number",
                            "description": "Duration in seconds (default: 5)",
                        },
                        "fps": {
                            "type": "number",
                            "description": "Frames per second to extract (default: 1)",
                        },
                        "max_frames": {
                            "type": "integer",
                            "description": "Maximum frames to extract (default: 8, max: 16)",
                        },
                    },
                    "required": ["video_path"],
                },
            },
            "cleanup_vision_frames": {
                "name": "cleanup_vision_frames",
                "description": "Remove temporary vision frames folder",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "run_id": {
                            "type": "string",
                            "description": "Specific run ID to clean up (optional, cleans all if empty)",
                        }
                    },
                },
            },
            "analyze_colors": {
                "name": "analyze_colors",
                "description": "Analyze video color characteristics (luminance, saturation, color balance)",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "video_path": {
                            "type": "string",
                            "description": "Path to video file",
                        },
                        "start": {
                            "type": "number",
                            "description": "Start time in seconds (default: 0)",
                        },
                        "duration": {
                            "type": "number",
                            "description": "Duration in seconds (default: 5)",
                        },
                    },
                    "required": ["video_path"],
                },
            },
            "analyze_audio": {
                "name": "analyze_audio",
                "description": "Analyze audio characteristics (volume, loudness, silence detection)",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "video_path": {
                            "type": "string",
                            "description": "Path to video/audio file",
                        },
                        "start": {
                            "type": "number",
                            "description": "Start time in seconds (default: 0)",
                        },
                        "duration": {
                            "type": "number",
                            "description": "Duration in seconds (default: 10)",
                        },
                    },
                    "required": ["video_path"],
                },
            },
            "list_luts": {
                "name": "list_luts",
                "description": "List available LUT files for color grading",
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                },
            },
        }

        self._resources = {
            "ffmpeg://commands/reference": {
                "uri": "ffmpeg://commands/reference",
                "name": "FFMPEG Command Reference",
                "description": "Complete FFMPEG command documentation",
                "mimeType": "application/json",
            },
            "ffmpeg://filters/list": {
                "uri": "ffmpeg://filters/list",
                "name": "FFMPEG Filters",
                "description": "Available video/audio filters",
                "mimeType": "application/json",
            },
            "ffmpeg://skills/registry": {
                "uri": "ffmpeg://skills/registry",
                "name": "Skill Registry",
                "description": "All registered editing skills",
                "mimeType": "application/json",
            },
            "ffmpeg://presets/list": {
                "uri": "ffmpeg://presets/list",
                "name": "Encoding Presets",
                "description": "Pre-built encoding presets",
                "mimeType": "application/json",
            },
        }

        # Store built pipelines for execution
        self._pipelines: dict[str, dict] = {}
        self._pipeline_counter = 0

        # Derive dispatch table from registered tools so they stay in sync
        self._dispatch: dict[str, str] = {
            name: f"_call_{name}" for name in self._tools
        }

    def list_tools(self) -> list[dict]:
        """List available MCP tools.

        Returns:
            List of tool definitions.
        """
        return list(self._tools.values())

    def list_resources(self) -> list[dict]:
        """List available MCP resources.

        Returns:
            List of resource definitions.
        """
        return list(self._resources.values())

    async def call_tool(self, name: str, arguments: dict) -> dict:
        """Call an MCP tool.

        Args:
            name: Tool name.
            arguments: Tool arguments.

        Returns:
            Tool result.
        """
        handler_name = self._dispatch.get(name)
        if not handler_name:
            return {"error": f"Unknown tool: {name}"}
        return await getattr(self, handler_name)(arguments)

    async def _call_analyze_video(self, arguments: dict) -> dict:
        """Handle analyze_video tool call."""
        video_path = arguments.get("video_path")
        if not video_path:
            return {"error": "video_path is required"}

        try:
            detail = arguments.get("detail", "full")
            result = analyze_video(video_path, detail=detail)
            return {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}
        except Exception as e:
            return {"error": str(e)}

    async def _call_list_skills(self, arguments: dict) -> dict:
        """Handle list_skills tool call."""
        category = arguments.get("category")

        try:
            result = list_skills(category)
            return {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}
        except Exception as e:
            return {"error": str(e)}

    async def _call_build_pipeline(self, arguments: dict) -> dict:
        """Handle build_pipeline tool call."""
        skills = arguments.get("skills", [])
        input_path = arguments.get("input_path")
        output_path = arguments.get("output_path")

        if not skills:
            return {"error": "skills list is required"}
        if not input_path:
            return {"error": "input_path is required"}
        if not output_path:
            return {"error": "output_path is required"}

        try:
            result = build_pipeline(skills, input_path, output_path)

            if not result.get("success"):
                return {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}

            # Store pipeline for execution
            self._pipeline_counter += 1
            pipeline_id = f"pipeline_{self._pipeline_counter}"
            self._pipelines[pipeline_id] = {
                "command": result["command"],
                "input_path": input_path,
                "output_path": output_path,
            }
            result["pipeline_id"] = pipeline_id

            return {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}
        except Exception as e:
            return {"error": str(e)}

    async def _call_execute_pipeline(self, arguments: dict) -> dict:
        """Handle execute_pipeline tool call."""
        pipeline_id = arguments.get("pipeline_id")

        if not pipeline_id:
            return {"error": "pipeline_id is required"}

        if pipeline_id not in self._pipelines:
            return {"error": f"Pipeline not found: {pipeline_id}"}

        pipeline = self._pipelines[pipeline_id]

        try:
            result = await execute_pipeline(pipeline["command"])
            return {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}
        except Exception as e:
            return {"error": str(e)}

    async def _call_search_skills(self, arguments: dict) -> dict:
        """Handle search_skills tool call."""
        query = arguments.get("query")
        if not query:
            return {"error": "query is required"}

        try:
            result = search_skills(query)
            return {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}
        except Exception as e:
            return {"error": str(e)}

    async def _call_get_skill_details(self, arguments: dict) -> dict:
        """Handle get_skill_details tool call."""
        skill_name = arguments.get("skill_name")
        if not skill_name:
            return {"error": "skill_name is required"}

        try:
            result = get_skill_details(skill_name)
            return {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}
        except Exception as e:
            return {"error": str(e)}

    async def _call_validate_skill_params(self, arguments: dict) -> dict:
        """Handle validate_skill_params tool call."""
        skill_name = arguments.get("skill_name")
        params = arguments.get("params", {})
        if not skill_name:
            return {"error": "skill_name is required"}

        try:
            result = validate_skill_params(skill_name, params)
            return {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}
        except Exception as e:
            return {"error": str(e)}

    async def _call_extract_frames(self, arguments: dict) -> dict:
        """Handle extract_frames tool call."""
        video_path = arguments.get("video_path")
        if not video_path:
            return {"error": "video_path is required"}

        try:
            result = extract_frames(
                video_path=video_path,
                start=arguments.get("start", 0.0),
                duration=arguments.get("duration", 5.0),
                fps=arguments.get("fps", 1.0),
                max_frames=arguments.get("max_frames", 8),
            )
            return {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}
        except Exception as e:
            return {"error": str(e)}

    async def _call_cleanup_vision_frames(self, arguments: dict) -> dict:
        """Handle cleanup_vision_frames tool call."""
        try:
            result = cleanup_vision_frames(run_id=arguments.get("run_id", ""))
            return {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}
        except Exception as e:
            return {"error": str(e)}

    async def _call_analyze_colors(self, arguments: dict) -> dict:
        """Handle analyze_colors tool call."""
        video_path = arguments.get("video_path")
        if not video_path:
            return {"error": "video_path is required"}

        try:
            result = analyze_colors(
                video_path=video_path,
                start=arguments.get("start", 0.0),
                duration=arguments.get("duration", 5.0),
            )
            return {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}
        except Exception as e:
            return {"error": str(e)}

    async def _call_analyze_audio(self, arguments: dict) -> dict:
        """Handle analyze_audio tool call."""
        video_path = arguments.get("video_path")
        if not video_path:
            return {"error": "video_path is required"}

        try:
            result = analyze_audio(
                video_path=video_path,
                start=arguments.get("start", 0.0),
                duration=arguments.get("duration", 10.0),
            )
            return {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}
        except Exception as e:
            return {"error": str(e)}

    async def _call_list_luts(self, arguments: dict) -> dict:
        """Handle list_luts tool call."""
        try:
            result = list_luts()
            return {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}
        except Exception as e:
            return {"error": str(e)}

    async def read_resource(self, uri: str) -> dict:
        """Read an MCP resource.

        Args:
            uri: Resource URI.

        Returns:
            Resource content.
        """
        if uri not in self._resources:
            return {"error": f"Unknown resource: {uri}"}

        try:
            content = get_resource(uri)
            return {
                "contents": [
                    {
                        "uri": uri,
                        "mimeType": "application/json",
                        "text": json.dumps(content, indent=2),
                    }
                ]
            }
        except Exception as e:
            return {"error": str(e)}


# Singleton server instance
_server: Optional[FFMPEGAMCPServer] = None


def get_server() -> FFMPEGAMCPServer:
    """Get the singleton MCP server instance.

    Returns:
        FFMPEGAMCPServer instance.
    """
    global _server
    if _server is None:
        _server = FFMPEGAMCPServer()
    return _server


async def handle_mcp_request(request: dict) -> dict:
    """Handle an MCP protocol request.

    Args:
        request: MCP request dictionary.

    Returns:
        MCP response dictionary.
    """
    server = get_server()
    method = request.get("method", "")

    if method == "tools/list":
        return {"tools": server.list_tools()}

    elif method == "tools/call":
        params = request.get("params", {})
        name = params.get("name", "")
        arguments = params.get("arguments", {})
        return await server.call_tool(name, arguments)

    elif method == "resources/list":
        return {"resources": server.list_resources()}

    elif method == "resources/read":
        params = request.get("params", {})
        uri = params.get("uri", "")
        return await server.read_resource(uri)

    else:
        return {"error": f"Unknown method: {method}"}
