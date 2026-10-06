#!/usr/bin/env python3
"""
⚠️ EDUCATIONAL DEMO: The "Stdio Trap" (Why print() Freezes Claude Desktop)

This file demonstrates the exact bug shown in Video 03:
A developer attempts quick debug inspection with standard `print()`.
Because stdio transport uses file descriptor 1 (stdout) for structured JSON-RPC bytes,
raw `print()` output injects unformatted text into the binary stream, causing:
  1. JSON parser deserialization failure on the client
  2. Silent connection hang / endless spinning wheel in Claude Desktop or Cursor
  3. Ghost processes that stay running in the background without serving requests

Compare this with server.py to see the proper sys.stderr logging fix!
"""

import asyncio
import json
import os
import sys

# ❌ FATAL MISTAKE: Raw debug print on startup!
# This writes to FD 1 (stdout) before the client even finishes the handshake!
print("[DEBUG] Initializing MCP Server in Python...")


async def main():
    print("[DEBUG] Attaching to stdin event loop...")

    loop = asyncio.get_running_loop()
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    await loop.connect_read_pipe(lambda: protocol, sys.stdin)

    while True:
        line_bytes = await reader.readline()
        if not line_bytes:
            break

        line = line_bytes.decode("utf-8").strip()
        if not line or not line.startswith("{"):
            continue

        request = json.loads(line)
        method = request.get("method")
        req_id = request.get("id")

        # ❌ FATAL MISTAKE: Printing request inspection to stdout!
        # Claude Desktop is expecting a pure JSON-RPC response object next.
        # Instead, it receives: "[DEBUG] Received tool method: ..."
        # Result: JSONDecodeError on client side -> Client deadlocks!
        print(f"[DEBUG] Received method: {method} with id: {req_id}")

        if method == "initialize":
            res = {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "buggy-mcp-server", "version": "0.1.0"},
                },
            }
            # Writing response back, but the stream is ALREADY corrupted by the print statements above!
            sys.stdout.write(json.dumps(res) + "\n")
            sys.stdout.flush()

        elif method == "tools/list":
            # ❌ Printing before answering tool lists
            print("[DEBUG] Serving tool list to client...")
            res = {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "tools": [
                        {
                            "name": "say_hello",
                            "description": "Greeting tool",
                            "inputSchema": {"type": "object", "properties": {}},
                        }
                    ]
                },
            }
            sys.stdout.write(json.dumps(res) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    print("==========================================================")
    print("⚠️ WARNING: This server contains the deliberate stdio trap!")
    print("Run this to reproduce client crashes, or use server.py for production.")
    print("==========================================================")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
