"""MCP Server implementation for FFMPEGA."""

import asyncio
import json
from typing import Any, Optional

from .tools import analyze_video, list_skills, build_pipeline, execute_pipeline
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
                        }
                    },
                    "required": ["video_path"],
                },
            },
            "list_skills": {
                "name": "list_skills",
                "description": "List available editing skills",
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
        if name == "analyze_video":
            return await self._call_analyze_video(arguments)
        elif name == "list_skills":
            return await self._call_list_skills(arguments)
        elif name == "build_pipeline":
            return await self._call_build_pipeline(arguments)
        elif name == "execute_pipeline":
            return await self._call_execute_pipeline(arguments)
        else:
            return {"error": f"Unknown tool: {name}"}

    async def _call_analyze_video(self, arguments: dict) -> dict:
        """Handle analyze_video tool call."""
        video_path = arguments.get("video_path")
        if not video_path:
            return {"error": "video_path is required"}

        try:
            result = analyze_video(video_path)
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
