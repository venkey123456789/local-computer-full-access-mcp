from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv(path: Path) -> None:
    """Tiny .env loader so the server does not need another dependency."""
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def _bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        return default
    return max(minimum, min(maximum, value))


def _split_roots(value: str) -> tuple[Path, ...]:
    # Accept semicolons everywhere because Windows drive letters make ':' awkward.
    chunks = [part.strip() for part in value.replace("\n", ";").split(";") if part.strip()]
    return tuple(Path(os.path.expandvars(os.path.expanduser(part))).resolve(strict=False) for part in chunks)


@dataclass(frozen=True)
class Settings:
    full_access: bool
    allowed_roots: tuple[Path, ...]
    transport: str
    host: str
    port: int
    endpoint_secret: str
    audit_log: Path
    data_dir: Path
    max_read_bytes: int
    max_write_bytes: int
    max_command_output_chars: int
    max_command_timeout_seconds: int
    allow_network_bind: bool

    @property
    def endpoint_path(self) -> str:
        return f"/mcp/{self.endpoint_secret}"

    @classmethod
    def load(cls) -> "Settings":
        project_dir = Path(__file__).resolve().parent.parent
        _load_dotenv(project_dir / ".env")

        data_dir = Path(
            os.path.expandvars(
                os.path.expanduser(os.getenv("PC_MCP_DATA_DIR", str(project_dir / ".data")))
            )
        ).resolve(strict=False)
        data_dir.mkdir(parents=True, exist_ok=True)

        roots_value = os.getenv("PC_MCP_ALLOWED_ROOTS", str(Path.home()))
        secret = os.getenv("PC_MCP_ENDPOINT_SECRET", "").strip() or secrets.token_urlsafe(32)
        transport = os.getenv("PC_MCP_TRANSPORT", "stdio").strip().lower()
        if transport not in {"stdio", "streamable-http"}:
            transport = "stdio"

        return cls(
            full_access=_bool("PC_MCP_FULL_ACCESS", False),
            allowed_roots=_split_roots(roots_value),
            transport=transport,
            host=os.getenv("PC_MCP_HOST", "127.0.0.1").strip() or "127.0.0.1",
            port=_int("PC_MCP_PORT", 8765, 1, 65535),
            endpoint_secret=secret,
            audit_log=Path(os.getenv("PC_MCP_AUDIT_LOG", str(data_dir / "audit.jsonl"))).resolve(strict=False),
            data_dir=data_dir,
            max_read_bytes=_int("PC_MCP_MAX_READ_BYTES", 2_000_000, 1_024, 100_000_000),
            max_write_bytes=_int("PC_MCP_MAX_WRITE_BYTES", 10_000_000, 1_024, 500_000_000),
            max_command_output_chars=_int("PC_MCP_MAX_COMMAND_OUTPUT_CHARS", 120_000, 1_000, 2_000_000),
            max_command_timeout_seconds=_int("PC_MCP_MAX_COMMAND_TIMEOUT_SECONDS", 900, 1, 86_400),
            allow_network_bind=_bool("PC_MCP_ALLOW_NETWORK_BIND", False),
        )
