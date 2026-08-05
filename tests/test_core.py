from pathlib import Path

import pytest

from pc_mcp.config import Settings
from pc_mcp.core import AccessDenied, LocalComputer


def make_pc(tmp_path: Path, full_access: bool = False) -> LocalComputer:
    settings = Settings(
        full_access=full_access,
        allowed_roots=(tmp_path.resolve(),),
        transport="stdio",
        host="127.0.0.1",
        port=8765,
        endpoint_secret="test-secret",
        audit_log=tmp_path / "audit.jsonl",
        data_dir=tmp_path / ".data",
        max_read_bytes=2_000_000,
        max_write_bytes=10_000_000,
        max_command_output_chars=120_000,
        max_command_timeout_seconds=30,
        allow_network_bind=False,
    )
    return LocalComputer(settings)


def test_write_read_replace_and_search(tmp_path: Path) -> None:
    pc = make_pc(tmp_path)
    file = tmp_path / "folder" / "hello.txt"
    pc.write_text_file(str(file), "hello world\nsecond line\n")
    read = pc.read_text_file(str(file))
    assert "hello world" in read["content"]
    pc.replace_text(str(file), "world", "MCP")
    assert file.read_text() == "hello MCP\nsecond line\n"
    results = pc.search_files(str(tmp_path), "MCP")
    assert results["results"][0]["path"] == str(file.resolve())


def test_guard_rejects_outside_root(tmp_path: Path) -> None:
    pc = make_pc(tmp_path)
    outside = tmp_path.parent / "outside.txt"
    with pytest.raises(AccessDenied):
        pc.file_info(str(outside))


def test_run_command(tmp_path: Path) -> None:
    pc = make_pc(tmp_path)
    result = pc.run_command("printf 'ready'", shell="bash")
    assert result["exit_code"] == 0
    assert result["stdout"] == "ready"


def test_delete_requires_recursive_for_nonempty_directory(tmp_path: Path) -> None:
    pc = make_pc(tmp_path)
    folder = tmp_path / "folder"
    folder.mkdir()
    (folder / "x.txt").write_text("x")
    with pytest.raises(OSError):
        pc.delete_path(str(folder), recursive=False)
    result = pc.delete_path(str(folder), recursive=True)
    assert result["deleted"] is True
    assert not folder.exists()
