#!/usr/bin/env python3
"""
Production-Ready Model Context Protocol (MCP) Server in Pure Python
Built from scratch with zero framework dependencies (No FastMCP, No MCP SDK).

Transport: stdio (sys.stdin, sys.stdout.buffer)
Logging: sys.stderr (strict stream isolation to prevent stdout protocol corruption)
Protocol: JSON-RPC 2.0 (LSP-style Content-Length framing & NDJSON support)
"""

import asyncio
import json
import logging
import os
import platform
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# ==============================================================================
# 1. LOGGING SETUP (STRICT STDERR SEPARATION)
# ==============================================================================
# RULE: Never use print() or write directly to stdout.
# Stdout (FD 1) is reserved strictly for framed JSON-RPC 2.0 byte packets.
# Stderr (FD 2) is the dedicated telemetry pipe for diagnostics and debugging.
logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("mcp-server")

SERVER_NAME = "python-mcp-from-scratch"
SERVER_VERSION = "1.0.0"
PROTOCOL_VERSION = "2024-11-05"


# ==============================================================================
# 2. TOOL DECLARATIONS (JSON SCHEMA DRAFT-07)
# ==============================================================================
# Tool schemas serve as the semantic contract with LLM clients (Claude, Cursor).
# Detailed descriptions guide model tool-selection vectors.
TOOLS: List[Dict[str, Any]] = [
    {
        "name": "get_system_stats",
        "description": "Returns host machine telemetry including OS architecture, Python runtime, uptime, and CPU core count.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "get_weather",
        "description": "Fetches current weather report and temperature telemetry for a specified city or location.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "City name or location query (e.g. 'San Francisco, CA', 'Tokyo', 'London')",
                },
                "unit": {
                    "type": "string",
                    "enum": ["celsius", "fahrenheit"],
                    "default": "celsius",
                    "description": "Temperature scale unit preference",
                },
            },
            "required": ["location"],
        },
    },
]


# ==============================================================================
# 3. TOOL EXECUTION HANDLERS
# ==============================================================================
async def handle_get_system_stats(arguments: Dict[str, Any]) -> str:
    """Telemetry tool: Gathers host platform diagnostic metrics."""
    logger.debug("Executing tool: get_system_stats")
    stats = {
        "platform": platform.platform(),
        "system": platform.system(),
        "release": platform.release(),
        "architecture": platform.machine(),
        "python_version": platform.python_version(),
        "cpu_count": os.cpu_count() or 1,
        "utc_time": datetime.now(timezone.utc).isoformat(),
    }
    return json.dumps(stats, indent=2)


async def handle_get_weather(arguments: Dict[str, Any]) -> str:
    """Weather tool: Returns telemetry data for requested location."""
    location = arguments.get("location", "").strip()
    unit = arguments.get("unit", "celsius").lower()
    
    if not location:
        raise ValueError("Missing required parameter: 'location'")

    logger.debug(f"Executing tool: get_weather for location='{location}', unit='{unit}'")

    # Deterministic mock simulation for clean reproducible demonstration
    loc_hash = sum(ord(c) for c in location)
    temp_c = 15 + (loc_hash % 18)
    conditions = ["Clear Sky", "Partly Cloudy", "Scattered Showers", "Overcast", "Sunny"]
    condition = conditions[loc_hash % len(conditions)]

    if unit == "fahrenheit":
        temp_disp = f"{(temp_c * 9 / 5) + 32:.1f}°F"
    else:
        temp_disp = f"{temp_c:.1f}°C"

    report = {
        "location": location,
        "temperature": temp_disp,
        "condition": condition,
        "humidity": f"{40 + (loc_hash % 50)}%",
        "wind_speed": f"{5 + (loc_hash % 20)} km/h",
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
    }
    return json.dumps(report, indent=2)


TOOL_DISPATCHER = {
    "get_system_stats": handle_get_system_stats,
    "get_weather": handle_get_weather,
}


# ==============================================================================
# 4. JSON-RPC 2.0 PROTOCOL ROUTER & ERROR HANDLING
# ==============================================================================
def make_error(req_id: Any, code: int, message: str, data: Optional[Any] = None) -> Dict[str, Any]:
    """Formats standardized JSON-RPC 2.0 error object.
    
    Standard codes:
      -32700: Parse error
      -32600: Invalid Request
      -32601: Method not found
      -32602: Invalid params
      -32603: Internal error (avoids client silent disconnect)
    """
    err_obj: Dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        err_obj["data"] = data
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": err_obj,
    }


def make_result(req_id: Any, result: Any) -> Dict[str, Any]:
    """Formats standardized JSON-RPC 2.0 success response."""
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "result": result,
    }


async def route_request(request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Dispatches incoming JSON-RPC methods according to MCP specification."""
    req_id = request.get("id")
    method = request.get("method")
    params = request.get("params", {})

    logger.info(f"Incoming RPC method='{method}' id={req_id}")

    # Notifications do not return responses (req_id is None)
    if method == "notifications/initialized":
        logger.info("Client acknowledged initialization. Ready for tool calls.")
        return None

    if method == "notifications/cancelled":
        logger.warning(f"Client cancelled operation: {params}")
        return None

    # Standard MCP Handshake: initialize
    if method == "initialize":
        client_version = params.get("protocolVersion")
        logger.info(f"Client requested handshake: protocolVersion={client_version}")
        return make_result(
            req_id,
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {
                    "tools": {
                        "listChanged": False,
                    },
                },
                "serverInfo": {
                    "name": SERVER_NAME,
                    "version": SERVER_VERSION,
                },
            },
        )

    # Ping method
    if method == "ping":
        return make_result(req_id, {})

    # Tool discovery: tools/list
    if method == "tools/list":
        logger.debug(f"Serving {len(TOOLS)} tool definitions to client.")
        return make_result(req_id, {"tools": TOOLS})

    # Tool execution: tools/call
    if method == "tools/call":
        tool_name = params.get("name")
        arguments = params.get("arguments", {})

        if not tool_name or tool_name not in TOOL_DISPATCHER:
            logger.error(f"Requested tool not found: '{tool_name}'")
            return make_error(req_id, -32601, f"Tool not found: '{tool_name}'")

        handler = TOOL_DISPATCHER[tool_name]
        try:
            content_text = await handler(arguments)
            return make_result(
                req_id,
                {
                    "content": [
                        {
                            "type": "text",
                            "text": content_text,
                        }
                    ],
                    "isError": False,
                },
            )
        except ValueError as e:
            logger.warning(f"Validation error in tool '{tool_name}': {e}")
            return make_error(req_id, -32602, f"Invalid params: {e}")
        except Exception as e:
            logger.exception(f"Unhandled exception in tool '{tool_name}': {e}")
            # Emitting -32603 ensures connection remains intact without client deadlock
            return make_error(req_id, -32603, f"Internal tool execution error: {str(e)}")

    # Unrecognized method
    if req_id is not None:
        logger.warning(f"Unrecognized method: '{method}'")
        return make_error(req_id, -32601, f"Method not found: '{method}'")

    return None


# ==============================================================================
# 5. ATOMIC BYTE FRAMING & STREAM I/O
# ==============================================================================
def write_framed_response(response: Dict[str, Any], use_lsp_headers: bool = True) -> None:
    """Formats and writes framed message directly to stdout buffer.
    
    UTF-8 TRAP AVOIDANCE:
      We calculate length using len(body_bytes), NOT len(body_string).
      Multi-byte characters and emojis cause character-count desync if decoded length is used.
    """
    body_str = json.dumps(response, ensure_ascii=False)
    body_bytes = body_str.encode("utf-8")

    if use_lsp_headers:
        # Standard LSP / MCP Content-Length double CRLF framing
        header = f"Content-Length: {len(body_bytes)}\r\n\r\n".encode("utf-8")
        packet = header + body_bytes
    else:
        # Fallback newline-delimited JSON (NDJSON)
        packet = body_bytes + b"\n"

    # Write atomic binary buffer directly to file descriptor 1
    sys.stdout.buffer.write(packet)
    # Immediately flush buffer to eliminate OS-level transmission lag
    sys.stdout.buffer.flush()
    logger.debug(f"Flushed {len(packet)} bytes to stdout.")


async def read_incoming_message(reader: asyncio.StreamReader) -> Optional[tuple[Dict[str, Any], bool]]:
    """Reads next JSON-RPC message from stream.
    
    Supports both:
      1. Content-Length header framed messages (LSP-style)
      2. Newline-delimited JSON messages (NDJSON)
      
    Returns tuple: (parsed_json_dict, used_lsp_framing_bool)
    """
    while True:
        line_bytes = await reader.readline()
        if not line_bytes:
            return None  # Stream closed by client

        line = line_bytes.decode("utf-8", errors="replace").strip()
        if not line:
            continue  # Skip extraneous empty newlines

        # Mode A: LSP Content-Length framing
        if line.lower().startswith("content-length:"):
            try:
                content_len = int(line.split(":", 1)[1].strip())
            except ValueError:
                logger.error(f"Malformed Content-Length header: '{line}'")
                continue

            # Read until empty line delimiter (\r\n\r\n)
            while True:
                separator = await reader.readline()
                if separator in (b"\r\n", b"\n", b""):
                    break

            payload_bytes = await reader.readexactly(content_len)
            payload_str = payload_bytes.decode("utf-8")
            return json.loads(payload_str), True

        # Mode B: Newline-delimited JSON line
        if line.startswith("{"):
            return json.loads(line), False

        logger.debug(f"Ignoring unrecognized raw stream preamble: '{line}'")


# ==============================================================================
# 6. ASYNCIO EVENT LOOP INITIALIZATION
# ==============================================================================
async def main() -> None:
    """Non-blocking event loop listening on standard input."""
    logger.info(f"Starting {SERVER_NAME} v{SERVER_VERSION} (Python {platform.python_version()})")
    logger.info("Stdio transport ready. Awaiting JSON-RPC requests on stdin...")

    # Attach non-blocking asynchronous reader to sys.stdin
    loop = asyncio.get_running_loop()
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    await loop.connect_read_pipe(lambda: protocol, sys.stdin)

    while True:
        try:
            read_result = await read_incoming_message(reader)
            if read_result is None:
                logger.info("Client stdin stream closed. Gracefully terminating server.")
                break

            request, used_lsp = read_result
            response = await route_request(request)

            if response is not None:
                write_framed_response(response, use_lsp_headers=used_lsp)

        except asyncio.IncompleteReadError:
            logger.info("Incomplete read detected (client closed stream). Exiting.")
            break
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON-RPC payload: {e}")
            err = make_error(None, -32700, f"Parse error: {e}")
            write_framed_response(err, use_lsp_headers=True)
        except Exception as e:
            logger.exception(f"Unexpected error in event loop: {e}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, BrokenPipeError):
        logger.info("Server halted.")
        sys.exit(0)
