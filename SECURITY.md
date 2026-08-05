# Security model

This server intentionally exposes the permissions of the Windows account that runs it. With `PC_MCP_FULL_ACCESS=1`, the `run_command` tool can do essentially anything that account can do: read or change files, install software, start programs, alter Git repositories, and run administration commands when the process itself is elevated.

## Non-negotiable rules

1. Keep `PC_MCP_HOST=127.0.0.1`. Do not open port 8765 in Windows Firewall or forward it from the router.
2. Never share the generated endpoint. Its long secret path acts as a capability token for the test setup.
3. Run the server as a normal Windows user. Do not run it as Administrator unless a specific task truly requires elevation.
4. Keep ChatGPT action confirmations enabled for write, delete, command, and process tools.
5. Stop `START_CHATGPT.bat` when finished. Close the launcher normally or run `STOP_MCP.bat`.
6. Review `.data/audit.jsonl` when an unexpected action occurs.
7. Rotate `PC_MCP_ENDPOINT_SECRET` immediately if the URL is copied into a public place.

## What the endpoint secret does—and does not do

The test setup uses a random URL path, `/mcp/<secret>`, because a TryCloudflare URL is temporary and ChatGPT can connect without a custom header. The launcher also rewrites the tunnel Host header back to the loopback origin so the MCP SDK can keep DNS-rebinding protection enabled. This prevents casual discovery but is not a replacement for OAuth on a permanent public deployment. Anyone who obtains the complete URL can invoke the server while it is running.

For a permanent deployment, use a stable HTTPS hostname plus MCP-compatible OAuth, strict identity policy, rate limiting, and logs. Do not publish an unauthenticated permanent endpoint with these tools.

## Safer restricted mode

Set:

```env
PC_MCP_FULL_ACCESS=0
PC_MCP_ALLOWED_ROOTS=%USERPROFILE%\\Documents;%USERPROFILE%\\Projects
```

All filesystem tools then reject paths outside those roots. Note that arbitrary shell execution can still reach other locations under the same Windows account; remove or disable `run_command` and `start_process` in `pc_mcp/server.py` for a genuinely filesystem-restricted deployment.
