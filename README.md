# Build an MCP Server from Scratch in Pure Python (No FastMCP)

> **Official Companion Repository** for the [@hackmyprompt](https://youtube.com/@hackmyprompt) video tutorial:  
> **"MCP Server Python: Fix the One-Line Bug That Freezes Claude Desktop"**  
> *(Video 03 in the AI Agent Engineering Series)*

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![Zero Dependencies](https://img.shields.io/badge/dependencies-0-brightgreen.svg)]()
[![Model Context Protocol](https://img.shields.io/badge/protocol-MCP%202024--11--05-purple.svg)](https://modelcontextprotocol.io/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

---

## 🎯 What This Repository Is

Most tutorials teach you how to build MCP servers using wrapper frameworks like **FastMCP** or the **MCP Python SDK**. While great for rapid prototyping, framework wrappers hide the wire mechanics. When your server silently freezes Claude Desktop or hangs Cursor, you have no idea why.

This repository demonstrates how to build a production-ready **Model Context Protocol (MCP)** server using **pure Python standard library** (`asyncio`, `json`, `sys`, `platform`).

- ❌ **No FastMCP**
- ❌ **No MCP Python SDK**
- ❌ **Zero external package dependencies**
- ✅ **100% Raw JSON-RPC 2.0 over `stdio`**

---

## 🏗️ The 4 Transport Pillars

```
┌─────────────────────────────────────────────────────────────────┐
│                      AI CLIENT (Claude / Cursor)                │
└───────────────▲─────────────────────────────────┬───────────────┘
                │ stdout (FD 1): Framed Packets   │ stdin: Requests
                │ Content-Length: N\r\n\r\n{...}  │
┌───────────────┴─────────────────────────────────▼───────────────┐
│              PYTHON MCP SERVER (server.py)                     │
│                                                                 │
│  [Pillar 1: JSON-RPC 2.0]     [Pillar 2: Asyncio Reader]        │
│   • initialize handshake       • non-blocking stdin listener    │
│   • tools/list discovery       • concurrent tool execution      │
│   • tools/call dispatch                                         │
│                                                                 │
│  [Pillar 3: UTF-8 Framing]    [Pillar 4: Stderr Isolation]      │
│   • len(str.encode('utf-8'))   • sys.stderr for all logs        │
│   • sys.stdout.buffer.flush()  • ZERO raw print() statements    │
└────────────────────────────────┬────────────────────────────────┘
                                 │ stderr (FD 2): Diagnostics
                                 ▼
                    DEVELOPER CONSOLE / LOGS
```

### 1. JSON-RPC 2.0 Wire Protocol
Every MCP interaction follows standard JSON-RPC 2.0 framing:
- **Handshake (`initialize`)**: Client announces capabilities; server returns version and supported features.
- **Discovery (`tools/list`)**: Server exposes tool declarations adhering to JSON Schema Draft 7.
- **Execution (`tools/call`)**: Client invokes tools; server dispatches and wraps return values.
- **Error Codes**: Unhandled errors return `-32603` (Internal Error) or `-32602` (Invalid Params) so the client explains errors to the user rather than hanging.

### 2. The Content-Length UTF-8 Trap
LSP and MCP over `stdio` prepend every payload with a `Content-Length` header:
```http
Content-Length: 124\r\n\r\n{"jsonrpc":"2.0",...}
```
> ⚠️ **The Trap**: You **cannot** use `len(json_string)`. Standard character length fails on multibyte Unicode characters and emojis (e.g. `len("🔥") == 1`, but `len("🔥".encode("utf-8")) == 4`). If character count is sent, client parsers desynchronize and hang forever.  
> **Always calculate UTF-8 byte count**: `len(message.encode('utf-8'))`.

### 3. File Descriptor Isolation (The "Stdio Trap")
- **File Descriptor 1 (`stdout`)**: Strictly reserved for framed protocol byte packets.
- **File Descriptor 2 (`stderr`)**: Reserved for developer diagnostics and logging.
- Writing raw `print("debug")` injects unformatted strings into stdout, breaking the client's JSON deserializer and freezing Claude Desktop.

### 4. Non-Blocking Asyncio Event Loop
MCP clients can dispatch parallel requests. Running synchronous blocking code delays tool replies. An `asyncio.StreamReader` attached to `sys.stdin` keeps the communication channel responsive.

---

## 📁 Repository Structure

```bash
├── server.py                   # Production MCP server (pure Python stdlib)
├── buggy_server.py             # Reproduces the "stdio print trap" deadlock
├── test_client.py              # Zero-dependency test client (runs over stdio)
├── claude_desktop_config.json  # Configuration snippet for Claude Desktop
├── cursor_config.json          # Configuration snippet for Cursor IDE
└── README.md
```

---

## ⚡ Quickstart

### 1. Run Automated Test Verification
You can test the entire JSON-RPC handshake and tool lifecycle immediately using the built-in test client:

```bash
python3 test_client.py
```

Expected output:
```text
=======================================================
🚀 Launching subprocess: python3 server.py
=======================================================
[Step 1] Sending 'initialize' handshake...
✅ Received initialize response
[Step 2] Sending 'notifications/initialized' notification...
[Step 3] Querying 'tools/list'...
✅ Discovered 2 tools: get_system_stats, get_weather
[Step 4] Calling tool 'get_system_stats'...
✅ System stats response content: { ... }
[Step 5] Calling tool 'get_weather'...
✅ Weather response content: { ... }
[Step 6] Testing schema validation error...
✅ Standardized error envelope received: -32602 Invalid params
=======================================================
🎉 ALL TESTS PASSED! Protocol framing is 100% verified.
=======================================================
```

---

### 2. Test with the Official MCP Inspector
Anthropic provides an official visual inspector to test MCP servers without caching interference:

```bash
npx @modelcontextprotocol/inspector python3 server.py
```

1. Open the local URL printed in your terminal (usually `http://localhost:5173`).
2. Click **Connect**.
3. Inspect `tools/list` and interactively trigger `get_system_stats` and `get_weather`.

---

### 3. Connect to Claude Desktop

1. Open your Claude Desktop configuration file:
   - **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
   - **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
   - **Linux**: `~/.config/Claude/claude_desktop_config.json`

2. Add the server entry:

```json
{
  "mcpServers": {
    "python-from-scratch": {
      "command": "python3",
      "args": [
        "/ABSOLUTE/PATH/TO/python-mcp-server-from-scratch/server.py"
      ]
    }
  }
}
```

3. Restart Claude Desktop.
4. Look for the 🔨 hammer icon in the chat prompt. Ask Claude:
   - *"What are my current system stats?"*
   - *"What is the weather in Tokyo?"*

---

### 4. Connect to Cursor IDE

1. Open **Cursor Settings** > **Features** > **MCP Servers**.
2. Click **+ Add New MCP Server**.
3. Name: `python-from-scratch`
4. Type: `command`
5. Command: `python3 /ABSOLUTE/PATH/TO/python-mcp-server-from-scratch/server.py`
6. Cursor will refresh and display the tools under its Composer tool tray.

---

## 💥 Reproduce the Bug (`buggy_server.py`)

To see why the "stdio trap" is so dangerous, test `buggy_server.py`:

```bash
python3 test_client.py buggy_server.py
```

You will see the JSON parser fail immediately because `print("[DEBUG] ...")` corrupted the stdout stream before the client could parse the handshake.

---

## 📺 Video Series

This is **Part 3** of our AI Engineering series on [@hackmyprompt](https://youtube.com/@hackmyprompt):

1. **Video 01**: [Python AI Chatbot in 5 Minutes](https://youtube.com/@hackmyprompt)
2. **Video 02**: [Structured Outputs: STOP Using json.loads() for OpenAI Tools](https://youtube.com/@hackmyprompt)
3. **Video 03**: **MCP Server Python: Fix the One-Line Bug That Freezes Claude Desktop** *(this repo)*
4. **Video 04**: Building Autonomous Multi-Tool AI Agents *(coming next)*

---

## 📄 License

MIT License. Free for commercial and personal educational use.
