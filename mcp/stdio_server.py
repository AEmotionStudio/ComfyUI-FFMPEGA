#!/usr/bin/env python3
"""Stdio transport wrapper for the FFMPEGA MCP server.

Implements JSON-RPC 2.0 over stdin/stdout per the MCP specification.

This script must be run from the project root directory, or with the
project root's parent on sys.path, so that the relative imports in
the ComfyUI-FFMPEGA package resolve correctly.

Usage (from project root):
    python -m mcp.stdio_server
"""

import asyncio
import json
import sys
import os


SERVER_NAME = "ffmpega"
SERVER_VERSION = "1.0.0"
PROTOCOL_VERSION = "2024-11-05"


def _setup_imports():
    """Set up imports so the FFMPEGA package can be loaded standalone.

    The mcp/ module uses relative imports like `from ..core.video.analyzer`
    which require the parent ComfyUI-FFMPEGA directory to be importable as
    a package. We achieve this by adding the ComfyUI custom_nodes dir to
    sys.path and importing the package by its directory name.
    """
    # This file lives at: ComfyUI-FFMPEGA/mcp/stdio_server.py
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    project_parent = os.path.dirname(project_root)
    package_name = os.path.basename(project_root)

    # Ensure the parent of the project is on sys.path
    if project_parent not in sys.path:
        sys.path.insert(0, project_parent)

    # Also add ComfyUI root so folder_paths can be found
    comfyui_root = os.path.dirname(project_parent)
    if os.path.isdir(comfyui_root) and comfyui_root not in sys.path:
        sys.path.insert(0, comfyui_root)

    # Now we can import the package properly
    # Using importlib to import the package with hyphens in the name
    # (directory name is "ComfyUI-FFMPEGA" which isn't valid Python,
    # so we import the submodules we need directly)
    return package_name, project_root


def make_response(req_id, result):
    """Create a JSON-RPC 2.0 response."""
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def make_error(req_id, code, message, data=None):
    """Create a JSON-RPC 2.0 error response."""
    error_obj: dict = {"code": code, "message": message}
    if data:
        error_obj["data"] = data
    return {"jsonrpc": "2.0", "id": req_id, "error": error_obj}


def _get_server(project_root):
    """Import and instantiate the FFMPEGA MCP server.

    We use importlib.util to load the server module directly since
    the package name contains hyphens.
    """
    import importlib.util

    # Load the server module directly
    server_path = os.path.join(project_root, "mcp", "server.py")

    # First, we need the parent package set up.
    # The simplest approach: temporarily manipulate sys.path so that
    # the project root IS the package root, and use absolute imports.
    # But the codebase uses relative imports. So we need to set up
    # the full package.

    # Actually, the cleanest way is to load via the package structure.
    # The project is under custom_nodes/, so if custom_nodes/ is on
    # sys.path, we can't import "ComfyUI-FFMPEGA" (invalid identifier).
    # Instead, let's create a proper package alias.

    package_name = os.path.basename(project_root)

    # Use spec_from_file_location to load the __init__.py
    init_path = os.path.join(project_root, "__init__.py")

    # Create a package spec - we'll register it under a clean name
    spec = importlib.util.spec_from_file_location(
        "comfyui_ffmpega",
        init_path,
        submodule_search_locations=[project_root],
    )
    if spec is None:
        raise RuntimeError(f"Could not create module spec from {init_path}")
    pkg = importlib.util.module_from_spec(spec)
    sys.modules["comfyui_ffmpega"] = pkg

    # Now set up the subpackages we need, so relative imports work
    # We need: core, core.video, core.executor, core.llm, skills, mcp, mcp.database, prompts
    subpackages = [
        "core",
        "core.video",
        "core.executor",
        "core.llm",
        "skills",
        "skills.category",
        "skills.outcome",
        "mcp",
        "mcp.database",
        "prompts",
    ]

    for sub in subpackages:
        sub_full = f"comfyui_ffmpega.{sub}"
        sub_path = os.path.join(project_root, sub.replace(".", os.sep))
        sub_init = os.path.join(sub_path, "__init__.py")

        if os.path.isfile(sub_init):
            sub_spec = importlib.util.spec_from_file_location(
                sub_full,
                sub_init,
                submodule_search_locations=[sub_path],
            )
            if sub_spec is not None:
                sub_mod = importlib.util.module_from_spec(sub_spec)
                sys.modules[sub_full] = sub_mod

    # Now execute the modules in dependency order
    # We need to exec the leaf modules that the server depends on
    _exec_module("comfyui_ffmpega.core")
    _exec_module("comfyui_ffmpega.core.video")
    _exec_module("comfyui_ffmpega.core.executor")
    _exec_module("comfyui_ffmpega.core.llm")
    _exec_module("comfyui_ffmpega.skills")
    _exec_module("comfyui_ffmpega.skills.category")
    _exec_module("comfyui_ffmpega.skills.outcome")
    _exec_module("comfyui_ffmpega.mcp.database")
    _exec_module("comfyui_ffmpega.prompts")
    _exec_module("comfyui_ffmpega.mcp")

    # Now we can import the server
    from comfyui_ffmpega.mcp.server import FFMPEGAMCPServer  # type: ignore[import-not-found]
    return FFMPEGAMCPServer()


def _exec_module(name: str) -> None:
    """Execute a registered module spec."""
    mod = sys.modules.get(name)
    if mod is None:
        return
    spec = getattr(mod, "__spec__", None)
    if spec is not None and spec.loader is not None:
        try:
            spec.loader.exec_module(mod)
        except Exception:
            pass  # Some modules may fail if optional deps missing


async def handle_request(request: dict, server) -> dict | None:
    """Handle a single JSON-RPC 2.0 request.

    Args:
        request: Parsed JSON-RPC request.
        server: FFMPEGAMCPServer instance.

    Returns:
        JSON-RPC response dict, or None for notifications.
    """
    req_id = request.get("id")
    method = request.get("method", "")
    params = request.get("params", {})

    # Notifications (no id) don't get responses
    if req_id is None:
        return None

    # --- Protocol methods ---

    if method == "initialize":
        return make_response(req_id, {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {
                "tools": {"listChanged": False},
                "resources": {"subscribe": False, "listChanged": False},
            },
            "serverInfo": {
                "name": SERVER_NAME,
                "version": SERVER_VERSION,
            },
        })

    elif method == "ping":
        return make_response(req_id, {})

    # --- Tool methods ---

    elif method == "tools/list":
        tools = server.list_tools()
        return make_response(req_id, {"tools": tools})

    elif method == "tools/call":
        name = params.get("name", "")
        arguments = params.get("arguments", {})
        try:
            result = await server.call_tool(name, arguments)
            if "error" in result:
                return make_response(req_id, {
                    "content": [{"type": "text", "text": json.dumps(result)}],
                    "isError": True,
                })
            return make_response(req_id, result)
        except Exception as e:
            return make_response(req_id, {
                "content": [{"type": "text", "text": f"Error: {e}"}],
                "isError": True,
            })

    # --- Resource methods ---

    elif method == "resources/list":
        resources = server.list_resources()
        return make_response(req_id, {"resources": resources})

    elif method == "resources/read":
        uri = params.get("uri", "")
        try:
            result = await server.read_resource(uri)
            if "error" in result:
                return make_error(req_id, -32602, result["error"])
            return make_response(req_id, result)
        except Exception as e:
            return make_error(req_id, -32603, str(e))

    else:
        return make_error(req_id, -32601, f"Method not found: {method}")


async def run_stdio():
    """Main stdio event loop — reads JSON-RPC from stdin, writes to stdout."""
    _package_name, project_root = _setup_imports()

    log = lambda msg: print(msg, file=sys.stderr, flush=True)
    log(f"FFMPEGA MCP Server v{SERVER_VERSION} starting...")

    try:
        server = _get_server(project_root)
    except Exception as e:
        log(f"Failed to initialize server: {e}")
        import traceback
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)

    log(f"FFMPEGA MCP Server v{SERVER_VERSION} started (stdio transport)")

    # Read from stdin line by line (each line is a JSON-RPC message)
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    await asyncio.get_event_loop().connect_read_pipe(lambda: protocol, sys.stdin)

    # Use stdout for writing
    writer_transport, writer_protocol = await asyncio.get_event_loop().connect_write_pipe(
        asyncio.Protocol, sys.stdout
    )
    writer = asyncio.StreamWriter(writer_transport, writer_protocol, reader, asyncio.get_event_loop())  # type: ignore[arg-type]

    while True:
        raw_line = await reader.readline()
        if not raw_line:
            break  # EOF

        line = raw_line.decode("utf-8").strip()
        if not line:
            continue

        try:
            request = json.loads(line)
        except json.JSONDecodeError as e:
            error_resp = make_error(None, -32700, f"Parse error: {e}")
            writer.write((json.dumps(error_resp) + "\n").encode("utf-8"))
            await writer.drain()
            continue

        response = await handle_request(request, server)

        if response is not None:
            writer.write((json.dumps(response) + "\n").encode("utf-8"))
            await writer.drain()

    log("FFMPEGA MCP Server shutting down")


def main():
    """Entry point."""
    try:
        asyncio.run(run_stdio())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
