# Local Computer Full-Access MCP

A Windows-first MCP server that gives an MCP client Codex-like local capabilities through explicit tools:

- unrestricted PowerShell, Command Prompt, or Bash commands;
- read, create, edit, copy, move, search, and delete files/directories;
- list drives and inspect disk capacity;
- start, inspect, and terminate processes;
- local JSONL audit logging;
- stdio transport for local MCP hosts;
- Streamable HTTP plus an HTTPS tunnel for ChatGPT;
- DNS-rebinding protection with tunnel Host-header rewriting;
- one-click shutdown via `STOP_MCP.bat`.

`run_command` makes this genuinely full access under the Windows account running the server. It is not a simulated filesystem.

> [!CAUTION]
> This project can execute arbitrary commands, modify or delete files, start processes, and expose everything accessible to the Windows account running it. Use it only on a computer you control. Keep the server bound to `127.0.0.1`, never publish the complete MCP endpoint URL, and stop the server when it is not in use. Read [SECURITY.md](SECURITY.md) before enabling full access.

## ChatGPT connectivity and availability

ChatGPT cannot connect directly to `127.0.0.1` on your PC. This package keeps the MCP service on localhost and uses `cloudflared` to create an outbound HTTPS tunnel for testing.

Availability of custom MCP apps and write/modify actions depends on the ChatGPT plan and workspace configuration and may change over time. Check OpenAI's current [developer mode and MCP apps documentation](https://help.openai.com/en/articles/12584461-developer-mode-and-full-mcp-connectors-in-chatgpt-beta). The server also works with compatible local MCP hosts over stdio.

## Install on Windows

1. Extract this folder to a permanent location, for example:

   `%USERPROFILE%\Documents\Local-Computer-Full-Access-MCP`

2. Double-click:

   `INSTALL_WINDOWS.bat`

The installer creates a Python virtual environment, installs the official MCP Python SDK, installs `cloudflared` through `winget` when needed, creates `.env`, enables full access because that is the requested mode, generates a random secret endpoint, and runs tests.

## Start for ChatGPT

1. Double-click `START_CHATGPT.bat`.
2. Keep the terminal window open.
3. Wait until it prints `CHATGPT MCP ENDPOINT`.
4. Copy the complete endpoint ending in `/mcp/<long-secret>`.
5. In a supported ChatGPT workspace on the web, enable Developer mode and create a custom app/MCP connector.
6. Paste the endpoint, choose **No authentication** for this temporary capability-URL setup, scan the tools, and create the app.
7. Enable the app in the chat. Leave confirmations enabled for risky actions.

To stop everything, close the launcher window normally or run `STOP_MCP.bat`.

The TryCloudflare hostname changes whenever the script restarts, so update the custom app endpoint after each restart. TryCloudflare is for testing, not a permanent deployment. If `cloudflared` reports that a Quick Tunnel cannot start because you already have `%USERPROFILE%\.cloudflared\config.yml` or `config.yaml`, temporarily rename that file or use a separately configured stable Cloudflare Tunnel.

## Start over stdio

Double-click `START_STDIO.bat`, or point a local MCP client at:

```text
command: <folder>\.venv\Scripts\python.exe
args: -m pc_mcp.server
environment: PC_MCP_TRANSPORT=stdio
```

An example generic client config is in `mcp-client-config.example.json`.

## Tools

Read-only tools:

- `pc_status`
- `list_drives`
- `file_info`
- `list_directory`
- `read_text_file`
- `read_binary_file_base64`
- `search_files`
- `list_processes`

Write/action tools:

- `write_text_file`
- `write_binary_file_base64`
- `replace_text`
- `make_directory`
- `copy_path`
- `move_path`
- `delete_path`
- `run_command`
- `start_process`
- `terminate_process`

## Example prompts after connection

- "Use my local-computer app to list my drives and show free space."
- "Inspect the selected project folder, run its tests, fix failures, and show me the changed files."
- "Search the selected project folder for references to a specified phrase without changing anything."
- "Create a backup of this folder before editing it. Ask before deleting anything."

## Configuration

The installer creates `.env`. Important settings:

```env
PC_MCP_FULL_ACCESS=1
PC_MCP_TRANSPORT=streamable-http
PC_MCP_HOST=127.0.0.1
PC_MCP_PORT=8765
PC_MCP_ENDPOINT_SECRET=<random-secret>
```

To restrict filesystem tools:

```env
PC_MCP_FULL_ACCESS=0
PC_MCP_ALLOWED_ROOTS=%USERPROFILE%\Documents;%USERPROFILE%\Projects
```

See `SECURITY.md` before leaving this server running or converting the test tunnel into a permanent endpoint.

## Test manually

Run `RUN_TESTS.bat`.

For MCP protocol inspection, activate the virtual environment and run:

```powershell
.\.venv\Scripts\Activate.ps1
mcp dev server.py
```

## Audit log

Tool actions and command outcomes that reach the core implementation are recorded locally at:

`.data\audit.jsonl`

File contents, binary payloads, and environment dictionaries are redacted and hashed in the audit record.
