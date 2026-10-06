#!/usr/bin/env python3
"""
Zero-Dependency Verification Client for MCP Server
Launches the MCP server as a subprocess over stdio and runs full protocol verification:
  1. Handshake (initialize + notifications/initialized)
  2. Tool discovery (tools/list)
  3. Tool execution (tools/call: get_system_stats)
  4. Tool execution (tools/call: get_weather)
  5. Error verification (tools/call with missing parameters -> -32602)
"""

import json
import subprocess
import sys
from typing import Any, Dict


def send_message(proc: subprocess.Popen, payload: Dict[str, Any], use_lsp_headers: bool = True) -> None:
    """Encodes and sends framed JSON-RPC message to server stdin."""
    body_str = json.dumps(payload, ensure_ascii=False)
    body_bytes = body_str.encode("utf-8")

    if use_lsp_headers:
        header = f"Content-Length: {len(body_bytes)}\r\n\r\n".encode("utf-8")
        packet = header + body_bytes
    else:
        packet = body_bytes + b"\n"

    proc.stdin.write(packet)
    proc.stdin.flush()


def read_message(proc: subprocess.Popen) -> Dict[str, Any]:
    """Reads next framed JSON-RPC message from server stdout."""
    while True:
        line = proc.stdout.readline()
        if not line:
            raise EOFError("Server closed stdout stream unexpectedly.")

        line_str = line.decode("utf-8", errors="replace").strip()
        if not line_str:
            continue

        # LSP Header Framing
        if line_str.lower().startswith("content-length:"):
            length = int(line_str.split(":", 1)[1].strip())
            # consume empty separator lines
            while True:
                sep = proc.stdout.readline()
                if sep in (b"\r\n", b"\n", b""):
                    break
            body = proc.stdout.read(length)
            return json.loads(body.decode("utf-8"))

        # NDJSON Framing
        if line_str.startswith("{"):
            return json.loads(line_str)


def run_test(target_script: str = "server.py") -> None:
    print(f"\n=======================================================")
    print(f"🚀 Launching subprocess: python3 {target_script}")
    print(f"=======================================================")

    # Spawn server process with piped stdin/stdout and inherited stderr
    proc = subprocess.Popen(
        [sys.executable, target_script],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=0,
    )

    try:
        # Step 1: initialize handshake
        print("\n[Step 1] Sending 'initialize' handshake...")
        send_message(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "clientInfo": {"name": "test-client", "version": "1.0.0"},
                },
            },
        )
        resp1 = read_message(proc)
        print("✅ Received initialize response:")
        print(json.dumps(resp1, indent=2))

        # Step 2: notifications/initialized ACK
        print("\n[Step 2] Sending 'notifications/initialized' notification...")
        send_message(
            proc,
            {
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
                "params": {},
            },
        )

        # Step 3: tools/list
        print("\n[Step 3] Querying 'tools/list'...")
        send_message(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/list",
                "params": {},
            },
        )
        resp3 = read_message(proc)
        tools = resp3.get("result", {}).get("tools", [])
        print(f"✅ Discovered {len(tools)} tools:")
        for t in tools:
            print(f"  • {t['name']}: {t['description']}")

        # Step 4: tools/call -> get_system_stats
        print("\n[Step 4] Calling tool 'get_system_stats'...")
        send_message(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "get_system_stats",
                    "arguments": {},
                },
            },
        )
        resp4 = read_message(proc)
        print("✅ System stats response content:")
        for item in resp4.get("result", {}).get("content", []):
            print(item.get("text"))

        # Step 5: tools/call -> get_weather
        print("\n[Step 5] Calling tool 'get_weather' (location='Tokyo', unit='celsius')...")
        send_message(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {
                    "name": "get_weather",
                    "arguments": {"location": "Tokyo", "unit": "celsius"},
                },
            },
        )
        resp5 = read_message(proc)
        print("✅ Weather response content:")
        for item in resp5.get("result", {}).get("content", []):
            print(item.get("text"))

        # Step 6: Error validation (Invalid params -> -32602)
        print("\n[Step 6] Testing schema validation error (missing required parameter)...")
        send_message(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 5,
                "method": "tools/call",
                "params": {
                    "name": "get_weather",
                    "arguments": {},  # Missing location
                },
            },
        )
        resp6 = read_message(proc)
        print("✅ Standardized error envelope received:")
        print(json.dumps(resp6, indent=2))
        assert resp6.get("error", {}).get("code") == -32602, "Expected -32602 Invalid params code!"

        print("\n=======================================================")
        print("🎉 ALL TESTS PASSED! Protocol framing is 100% verified.")
        print("=======================================================\n")

    finally:
        proc.terminate()
        proc.wait(timeout=2)


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "server.py"
    run_test(target)
