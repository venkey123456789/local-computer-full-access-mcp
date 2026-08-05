from __future__ import annotations

import os
from typing import Any

from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings

from .config import Settings
from .core import LocalComputer

settings = Settings.load()
pc = LocalComputer(settings)

mcp = MCPServer(
    "local-computer-full-access",
    version="1.0.0",
    instructions=(
        "This server controls the user's own computer. Prefer inspection before mutation. "
        "Explain destructive operations clearly and use the host's confirmation flow. "
        "Use filesystem tools for precise edits and run_command for builds, tests, package managers, Git, and system administration. "
        "Never claim an operation succeeded unless the returned result confirms it."
    ),
)


@mcp.tool()
def pc_status() -> dict[str, Any]:
    """Inspect this MCP server, computer identity, access mode, roots, endpoint, and audit-log location. Read-only."""
    return pc.status()


@mcp.tool()
def list_drives() -> list[dict[str, Any]]:
    """List mounted disks/drives and their capacity. Read-only."""
    return pc.list_drives()


@mcp.tool()
def file_info(path: str) -> dict[str, Any]:
    """Return metadata for one file, directory, or symbolic link. Read-only."""
    return pc.file_info(path)


@mcp.tool()
def list_directory(path: str, recursive: bool = False, max_entries: int = 500) -> dict[str, Any]:
    """List a directory. Set recursive=true only when needed; max_entries prevents huge responses. Read-only."""
    return pc.list_directory(path, recursive, max_entries)


@mcp.tool()
def read_text_file(path: str, encoding: str = "utf-8", start_line: int = 1, max_lines: int = 4000) -> dict[str, Any]:
    """Read a text file with line-window controls. Read-only."""
    return pc.read_text_file(path, encoding, start_line, max_lines)


@mcp.tool()
def read_binary_file_base64(path: str, max_bytes: int = 5_000_000) -> dict[str, Any]:
    """Read a small binary file and return base64. Read-only; intended for files that cannot be handled as text."""
    return pc.read_binary_file_base64(path, max_bytes)


@mcp.tool()
def write_text_file(path: str, content: str, overwrite: bool = False, create_parents: bool = True, encoding: str = "utf-8") -> dict[str, Any]:
    """Create or overwrite a text file. This modifies the computer. Existing files require overwrite=true."""
    return pc.write_text_file(path, content, overwrite, create_parents, encoding)


@mcp.tool()
def write_binary_file_base64(path: str, data_base64: str, overwrite: bool = False, create_parents: bool = True) -> dict[str, Any]:
    """Create or overwrite a binary file from base64. This modifies the computer. Existing files require overwrite=true."""
    return pc.write_binary_file_base64(path, data_base64, overwrite, create_parents)


@mcp.tool()
def replace_text(path: str, old_text: str, new_text: str, replace_all: bool = False, encoding: str = "utf-8") -> dict[str, Any]:
    """Make an exact text replacement in a file. This modifies the computer and refuses ambiguous multiple matches unless replace_all=true."""
    return pc.replace_text(path, old_text, new_text, replace_all, encoding)


@mcp.tool()
def make_directory(path: str, parents: bool = True, exist_ok: bool = True) -> dict[str, Any]:
    """Create a directory. This modifies the computer."""
    return pc.make_directory(path, parents, exist_ok)


@mcp.tool()
def copy_path(source: str, destination: str, overwrite: bool = False) -> dict[str, Any]:
    """Copy a file or directory. This modifies the computer. Existing destinations require overwrite=true."""
    return pc.copy_path(source, destination, overwrite)


@mcp.tool()
def move_path(source: str, destination: str, overwrite: bool = False) -> dict[str, Any]:
    """Move or rename a file or directory. This modifies the computer. Existing destinations require overwrite=true."""
    return pc.move_path(source, destination, overwrite)


@mcp.tool()
def delete_path(path: str, recursive: bool = False, missing_ok: bool = False) -> dict[str, Any]:
    """Delete a file, empty directory, or—when recursive=true—a directory tree. DESTRUCTIVE and irreversible outside backups."""
    return pc.delete_path(path, recursive, missing_ok)


@mcp.tool()
def search_files(
    root: str,
    query: str,
    glob: str = "*",
    search_contents: bool = True,
    case_sensitive: bool = False,
    max_results: int = 200,
    max_file_bytes: int = 2_000_000,
) -> dict[str, Any]:
    """Search filenames and optionally UTF-8-compatible text contents below a root directory. Read-only."""
    return pc.search_files(root, query, glob, search_contents, case_sensitive, max_results, max_file_bytes)


@mcp.tool()
def run_command(
    command: str,
    cwd: str | None = None,
    timeout_seconds: int = 120,
    shell: str = "auto",
    environment: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Run an arbitrary PowerShell/cmd/bash command and wait for completion. FULL-ACCESS tool: commands run with the Windows account permissions of this server. Use shell=auto normally."""
    return pc.run_command(command, cwd, timeout_seconds, shell, environment)


@mcp.tool()
def start_process(
    command: str,
    cwd: str | None = None,
    shell: str = "auto",
    environment: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Start a long-running command in the background and return its PID and log path. FULL-ACCESS tool."""
    return pc.start_process(command, cwd, shell, environment)


@mcp.tool()
def list_processes(name_filter: str = "", max_results: int = 300) -> dict[str, Any]:
    """List running processes, optionally filtered by name or command line. Read-only."""
    return pc.list_processes(name_filter, max_results)


@mcp.tool()
def terminate_process(pid: int, force: bool = False, include_children: bool = False) -> dict[str, Any]:
    """Terminate or force-kill a process and optionally its descendants. DESTRUCTIVE; may cause data loss."""
    return pc.terminate_process(pid, force, include_children)


def main() -> None:
    if settings.transport == "streamable-http":
        if settings.host not in {"127.0.0.1", "localhost", "::1"} and not settings.allow_network_bind:
            raise RuntimeError(
                "Refusing a non-loopback bind. Keep PC_MCP_HOST=127.0.0.1 and use an authenticated/restricted tunnel. "
                "To deliberately bind a LAN/WAN interface, set PC_MCP_ALLOW_NETWORK_BIND=1."
            )
        print(
            f"Local Computer MCP listening at http://{settings.host}:{settings.port}{settings.endpoint_path}",
            file=os.sys.stderr,
            flush=True,
        )
        # Keep DNS-rebinding protection enabled. The ChatGPT launcher tells
        # cloudflared to rewrite the origin Host header back to this loopback
        # address, so public tunnel hostnames never need to be allowlisted here.
        transport_security = TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=[
                f"{settings.host}:*",
                "127.0.0.1:*",
                "localhost:*",
                "[::1]:*",
            ],
            allowed_origins=[
                "http://127.0.0.1:*",
                "http://localhost:*",
                "https://chatgpt.com",
                "https://www.chatgpt.com",
            ],
        )
        mcp.run(
            transport="streamable-http",
            host=settings.host,
            port=settings.port,
            streamable_http_path=settings.endpoint_path,
            max_request_body_size=4 * 1024 * 1024,
            transport_security=transport_security,
        )
    else:
        mcp.run()


if __name__ == "__main__":
    main()
