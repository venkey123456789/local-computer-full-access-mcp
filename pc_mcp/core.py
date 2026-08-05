from __future__ import annotations

import base64
import fnmatch
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import psutil

from .config import Settings


class AccessDenied(PermissionError):
    pass


class LocalComputer:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.settings.audit_log.parent.mkdir(parents=True, exist_ok=True)
        (self.settings.data_dir / "processes").mkdir(parents=True, exist_ok=True)

    def _audit(self, tool: str, arguments: dict[str, Any], outcome: str, detail: str = "") -> None:
        safe_args: dict[str, Any] = {}
        for key, value in arguments.items():
            if key in {"content", "data_base64", "environment"}:
                text = json.dumps(value, default=str, ensure_ascii=False)
                safe_args[key] = {
                    "redacted": True,
                    "length": len(text),
                    "sha256": hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest(),
                }
            else:
                safe_args[key] = value
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tool": tool,
            "arguments": safe_args,
            "outcome": outcome,
            "detail": detail[:2000],
            "pid": os.getpid(),
        }
        with self.settings.audit_log.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")

    def _expand_path(self, raw_path: str | Path) -> Path:
        if isinstance(raw_path, Path):
            value = str(raw_path)
        else:
            value = raw_path
        if not value or not value.strip():
            raise ValueError("path must not be empty")
        expanded = os.path.expandvars(os.path.expanduser(value.strip()))
        return Path(expanded).resolve(strict=False)

    @staticmethod
    def _is_within(path: Path, root: Path) -> bool:
        try:
            return os.path.commonpath([str(path), str(root)]) == str(root)
        except ValueError:
            return False

    def checked_path(self, raw_path: str | Path, *, must_exist: bool = False) -> Path:
        path = self._expand_path(raw_path)
        if not self.settings.full_access and not any(self._is_within(path, root) for root in self.settings.allowed_roots):
            raise AccessDenied(
                f"Path is outside PC_MCP_ALLOWED_ROOTS: {path}. "
                "Set PC_MCP_FULL_ACCESS=1 only when you intentionally want unrestricted access."
            )
        if must_exist and not path.exists():
            raise FileNotFoundError(str(path))
        return path

    @staticmethod
    def _file_record(path: Path) -> dict[str, Any]:
        stat = path.lstat()
        return {
            "path": str(path),
            "name": path.name,
            "type": "symlink" if path.is_symlink() else "directory" if path.is_dir() else "file",
            "size": stat.st_size,
            "modified": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
            "created": datetime.fromtimestamp(stat.st_ctime, timezone.utc).isoformat(),
            "mode": oct(stat.st_mode),
        }

    def status(self) -> dict[str, Any]:
        roots = [str(root) for root in self.settings.allowed_roots]
        result = {
            "server_version": "1.0.0",
            "platform": platform.platform(),
            "python": sys.version.split()[0],
            "hostname": platform.node(),
            "username": os.getenv("USERNAME") or os.getenv("USER") or "unknown",
            "working_directory": str(Path.cwd()),
            "full_access": self.settings.full_access,
            "allowed_roots": roots,
            "transport": self.settings.transport,
            "http_listen": f"http://{self.settings.host}:{self.settings.port}{self.settings.endpoint_path}",
            "audit_log": str(self.settings.audit_log),
            "process_id": os.getpid(),
        }
        self._audit("pc_status", {}, "ok")
        return result

    def list_drives(self) -> list[dict[str, Any]]:
        drives: list[dict[str, Any]] = []
        seen: set[str] = set()
        for part in psutil.disk_partitions(all=False):
            if part.mountpoint in seen:
                continue
            seen.add(part.mountpoint)
            try:
                usage = psutil.disk_usage(part.mountpoint)
            except (PermissionError, OSError):
                usage = None
            drives.append(
                {
                    "device": part.device,
                    "mountpoint": part.mountpoint,
                    "filesystem": part.fstype,
                    "options": part.opts,
                    "total": usage.total if usage else None,
                    "used": usage.used if usage else None,
                    "free": usage.free if usage else None,
                    "percent": usage.percent if usage else None,
                }
            )
        self._audit("list_drives", {}, "ok", f"{len(drives)} drives")
        return drives

    def file_info(self, path: str) -> dict[str, Any]:
        target = self.checked_path(path, must_exist=True)
        result = self._file_record(target)
        if target.is_file():
            result["suffix"] = target.suffix
        self._audit("file_info", {"path": path}, "ok")
        return result

    def list_directory(self, path: str, recursive: bool = False, max_entries: int = 500) -> dict[str, Any]:
        target = self.checked_path(path, must_exist=True)
        if not target.is_dir():
            raise NotADirectoryError(str(target))
        max_entries = max(1, min(max_entries, 10_000))
        entries: list[dict[str, Any]] = []
        iterator: Iterable[Path]
        iterator = target.rglob("*") if recursive else target.iterdir()
        for child in iterator:
            try:
                entries.append(self._file_record(child))
            except (FileNotFoundError, PermissionError, OSError) as exc:
                entries.append({"path": str(child), "error": str(exc)})
            if len(entries) >= max_entries:
                break
        entries.sort(key=lambda item: (item.get("type") != "directory", str(item.get("name", "")).lower()))
        result = {"directory": str(target), "recursive": recursive, "entries": entries, "truncated": len(entries) >= max_entries}
        self._audit("list_directory", {"path": path, "recursive": recursive, "max_entries": max_entries}, "ok", f"{len(entries)} entries")
        return result

    def read_text_file(self, path: str, encoding: str = "utf-8", start_line: int = 1, max_lines: int = 4000) -> dict[str, Any]:
        target = self.checked_path(path, must_exist=True)
        if not target.is_file():
            raise IsADirectoryError(str(target))
        size = target.stat().st_size
        if size > self.settings.max_read_bytes:
            raise ValueError(f"File is {size} bytes; limit is {self.settings.max_read_bytes}. Use command tools for deliberate large-file processing.")
        start_line = max(1, start_line)
        max_lines = max(1, min(max_lines, 100_000))
        selected: list[str] = []
        total_lines = 0
        with target.open("r", encoding=encoding, errors="replace") as handle:
            for index, line in enumerate(handle, start=1):
                total_lines = index
                if index < start_line:
                    continue
                if len(selected) >= max_lines:
                    break
                selected.append(line)
        content = "".join(selected)
        result = {
            "path": str(target),
            "encoding": encoding,
            "start_line": start_line,
            "lines_returned": len(selected),
            "total_lines_seen": total_lines,
            "content": content,
            "truncated": len(selected) >= max_lines,
        }
        self._audit("read_text_file", {"path": path, "encoding": encoding, "start_line": start_line, "max_lines": max_lines}, "ok", f"{len(content)} chars")
        return result

    def read_binary_file_base64(self, path: str, max_bytes: int = 5_000_000) -> dict[str, Any]:
        target = self.checked_path(path, must_exist=True)
        if not target.is_file():
            raise IsADirectoryError(str(target))
        max_bytes = max(1, min(max_bytes, self.settings.max_read_bytes))
        size = target.stat().st_size
        if size > max_bytes:
            raise ValueError(f"Binary file is {size} bytes; requested limit is {max_bytes} bytes")
        data = target.read_bytes()
        result = {"path": str(target), "size": len(data), "base64": base64.b64encode(data).decode("ascii")}
        self._audit("read_binary_file_base64", {"path": path, "max_bytes": max_bytes}, "ok", f"{len(data)} bytes")
        return result

    def write_text_file(self, path: str, content: str, overwrite: bool = False, create_parents: bool = True, encoding: str = "utf-8") -> dict[str, Any]:
        data = content.encode(encoding)
        if len(data) > self.settings.max_write_bytes:
            raise ValueError(f"Write is {len(data)} bytes; limit is {self.settings.max_write_bytes}")
        target = self.checked_path(path)
        if target.exists() and not overwrite:
            raise FileExistsError(f"Refusing to overwrite existing path without overwrite=true: {target}")
        if target.exists() and target.is_dir():
            raise IsADirectoryError(str(target))
        if create_parents:
            target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding=encoding)
        result = {"path": str(target), "bytes_written": len(data), "overwritten": overwrite}
        self._audit("write_text_file", {"path": path, "content": content, "overwrite": overwrite, "create_parents": create_parents, "encoding": encoding}, "ok")
        return result

    def write_binary_file_base64(self, path: str, data_base64: str, overwrite: bool = False, create_parents: bool = True) -> dict[str, Any]:
        try:
            data = base64.b64decode(data_base64, validate=True)
        except Exception as exc:
            raise ValueError("data_base64 is not valid base64") from exc
        if len(data) > self.settings.max_write_bytes:
            raise ValueError(f"Write is {len(data)} bytes; limit is {self.settings.max_write_bytes}")
        target = self.checked_path(path)
        if target.exists() and not overwrite:
            raise FileExistsError(f"Refusing to overwrite existing path without overwrite=true: {target}")
        if create_parents:
            target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        result = {"path": str(target), "bytes_written": len(data), "overwritten": overwrite}
        self._audit("write_binary_file_base64", {"path": path, "data_base64": data_base64, "overwrite": overwrite, "create_parents": create_parents}, "ok")
        return result

    def replace_text(self, path: str, old_text: str, new_text: str, replace_all: bool = False, encoding: str = "utf-8") -> dict[str, Any]:
        if not old_text:
            raise ValueError("old_text must not be empty")
        target = self.checked_path(path, must_exist=True)
        text = target.read_text(encoding=encoding)
        count = text.count(old_text)
        if count == 0:
            raise ValueError("old_text was not found")
        if count > 1 and not replace_all:
            raise ValueError(f"old_text occurs {count} times; set replace_all=true or provide a more specific match")
        updated = text.replace(old_text, new_text) if replace_all else text.replace(old_text, new_text, 1)
        encoded = updated.encode(encoding)
        if len(encoded) > self.settings.max_write_bytes:
            raise ValueError(f"Updated file would be {len(encoded)} bytes; limit is {self.settings.max_write_bytes}")
        target.write_text(updated, encoding=encoding)
        replacements = count if replace_all else 1
        result = {"path": str(target), "replacements": replacements, "bytes_written": len(encoded)}
        self._audit("replace_text", {"path": path, "old_text": old_text, "new_text": new_text, "replace_all": replace_all, "encoding": encoding}, "ok")
        return result

    def make_directory(self, path: str, parents: bool = True, exist_ok: bool = True) -> dict[str, Any]:
        target = self.checked_path(path)
        target.mkdir(parents=parents, exist_ok=exist_ok)
        result = {"path": str(target), "created": True}
        self._audit("make_directory", {"path": path, "parents": parents, "exist_ok": exist_ok}, "ok")
        return result

    def copy_path(self, source: str, destination: str, overwrite: bool = False) -> dict[str, Any]:
        src = self.checked_path(source, must_exist=True)
        dst = self.checked_path(destination)
        if dst.exists():
            if not overwrite:
                raise FileExistsError(f"Destination exists; set overwrite=true: {dst}")
            if dst.is_dir() and not dst.is_symlink():
                shutil.rmtree(dst)
            else:
                dst.unlink()
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir() and not src.is_symlink():
            shutil.copytree(src, dst, symlinks=True)
        else:
            shutil.copy2(src, dst, follow_symlinks=False)
        result = {"source": str(src), "destination": str(dst)}
        self._audit("copy_path", {"source": source, "destination": destination, "overwrite": overwrite}, "ok")
        return result

    def move_path(self, source: str, destination: str, overwrite: bool = False) -> dict[str, Any]:
        src = self.checked_path(source, must_exist=True)
        dst = self.checked_path(destination)
        if dst.exists():
            if not overwrite:
                raise FileExistsError(f"Destination exists; set overwrite=true: {dst}")
            if dst.is_dir() and not dst.is_symlink():
                shutil.rmtree(dst)
            else:
                dst.unlink()
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        result = {"source": str(src), "destination": str(dst)}
        self._audit("move_path", {"source": source, "destination": destination, "overwrite": overwrite}, "ok")
        return result

    def delete_path(self, path: str, recursive: bool = False, missing_ok: bool = False) -> dict[str, Any]:
        target = self.checked_path(path)
        if not target.exists() and not target.is_symlink():
            if missing_ok:
                return {"path": str(target), "deleted": False, "reason": "missing"}
            raise FileNotFoundError(str(target))
        if target.is_dir() and not target.is_symlink():
            if not recursive:
                target.rmdir()
            else:
                shutil.rmtree(target)
        else:
            target.unlink()
        result = {"path": str(target), "deleted": True}
        self._audit("delete_path", {"path": path, "recursive": recursive, "missing_ok": missing_ok}, "ok")
        return result

    def search_files(
        self,
        root: str,
        query: str,
        glob: str = "*",
        search_contents: bool = True,
        case_sensitive: bool = False,
        max_results: int = 200,
        max_file_bytes: int = 2_000_000,
    ) -> dict[str, Any]:
        base = self.checked_path(root, must_exist=True)
        if not base.is_dir():
            raise NotADirectoryError(str(base))
        if not query:
            raise ValueError("query must not be empty")
        max_results = max(1, min(max_results, 5000))
        max_file_bytes = max(1, min(max_file_bytes, self.settings.max_read_bytes))
        needle = query if case_sensitive else query.lower()
        results: list[dict[str, Any]] = []
        scanned = 0
        for path in base.rglob("*"):
            if len(results) >= max_results:
                break
            try:
                resolved = path.resolve(strict=False)
                if resolved == self.settings.audit_log or self._is_within(resolved, self.settings.data_dir):
                    continue
            except OSError:
                continue
            if not path.is_file() or not fnmatch.fnmatch(path.name, glob):
                continue
            scanned += 1
            name_haystack = path.name if case_sensitive else path.name.lower()
            if needle in name_haystack:
                results.append({"path": str(path), "match": "filename"})
                continue
            if not search_contents:
                continue
            try:
                if path.stat().st_size > max_file_bytes:
                    continue
                with path.open("r", encoding="utf-8", errors="ignore") as handle:
                    for line_number, line in enumerate(handle, start=1):
                        haystack = line if case_sensitive else line.lower()
                        if needle in haystack:
                            results.append({"path": str(path), "match": "content", "line": line_number, "preview": line.strip()[:500]})
                            break
            except (PermissionError, OSError):
                continue
        result = {"root": str(base), "query": query, "glob": glob, "scanned_files": scanned, "results": results, "truncated": len(results) >= max_results}
        self._audit("search_files", {"root": root, "query": query, "glob": glob, "search_contents": search_contents, "case_sensitive": case_sensitive, "max_results": max_results, "max_file_bytes": max_file_bytes}, "ok", f"{len(results)} matches")
        return result

    @staticmethod
    def _command_argv(command: str, shell: str) -> list[str]:
        if not command.strip():
            raise ValueError("command must not be empty")
        shell = shell.lower().strip()
        if shell == "auto":
            shell = "powershell" if os.name == "nt" else "bash"
        if shell == "powershell":
            executable = shutil.which("pwsh") or shutil.which("powershell.exe") or shutil.which("powershell")
            if not executable:
                raise FileNotFoundError("PowerShell was not found")
            return [executable, "-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", command]
        if shell == "cmd":
            executable = shutil.which("cmd.exe") or shutil.which("cmd")
            if not executable:
                raise FileNotFoundError("cmd.exe was not found")
            return [executable, "/d", "/s", "/c", command]
        if shell == "bash":
            executable = shutil.which("bash")
            if not executable:
                raise FileNotFoundError("bash was not found")
            return [executable, "-lc", command]
        raise ValueError("shell must be one of: auto, powershell, cmd, bash")

    def _truncate(self, text: str) -> tuple[str, bool]:
        limit = self.settings.max_command_output_chars
        if len(text) <= limit:
            return text, False
        head = limit // 2
        tail = limit - head
        return text[:head] + "\n\n... OUTPUT TRUNCATED ...\n\n" + text[-tail:], True

    def run_command(
        self,
        command: str,
        cwd: str | None = None,
        timeout_seconds: int = 120,
        shell: str = "auto",
        environment: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        workdir = self.checked_path(cwd, must_exist=True) if cwd else None
        if workdir and not workdir.is_dir():
            raise NotADirectoryError(str(workdir))
        timeout_seconds = max(1, min(timeout_seconds, self.settings.max_command_timeout_seconds))
        argv = self._command_argv(command, shell)
        env = os.environ.copy()
        if environment:
            env.update({str(key): str(value) for key, value in environment.items()})
        started = time.monotonic()
        try:
            completed = subprocess.run(
                argv,
                cwd=str(workdir) if workdir else None,
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout_seconds,
                shell=False,
            )
            duration = round(time.monotonic() - started, 3)
            stdout, stdout_truncated = self._truncate(completed.stdout)
            stderr, stderr_truncated = self._truncate(completed.stderr)
            result = {
                "command": command,
                "shell": shell,
                "cwd": str(workdir) if workdir else str(Path.cwd()),
                "exit_code": completed.returncode,
                "duration_seconds": duration,
                "stdout": stdout,
                "stderr": stderr,
                "stdout_truncated": stdout_truncated,
                "stderr_truncated": stderr_truncated,
            }
            self._audit("run_command", {"command": command, "cwd": cwd, "timeout_seconds": timeout_seconds, "shell": shell, "environment": environment or {}}, "ok" if completed.returncode == 0 else "nonzero", f"exit={completed.returncode}")
            return result
        except subprocess.TimeoutExpired as exc:
            duration = round(time.monotonic() - started, 3)
            self._audit("run_command", {"command": command, "cwd": cwd, "timeout_seconds": timeout_seconds, "shell": shell, "environment": environment or {}}, "timeout", f"after {duration}s")
            return {
                "command": command,
                "shell": shell,
                "cwd": str(workdir) if workdir else str(Path.cwd()),
                "timed_out": True,
                "duration_seconds": duration,
                "stdout": (exc.stdout or "") if isinstance(exc.stdout, str) else "",
                "stderr": (exc.stderr or "") if isinstance(exc.stderr, str) else "",
            }

    def start_process(
        self,
        command: str,
        cwd: str | None = None,
        shell: str = "auto",
        environment: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        workdir = self.checked_path(cwd, must_exist=True) if cwd else None
        argv = self._command_argv(command, shell)
        env = os.environ.copy()
        if environment:
            env.update({str(key): str(value) for key, value in environment.items()})
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        log_path = self.settings.data_dir / "processes" / f"process-{stamp}-{os.getpid()}.log"
        log_handle = log_path.open("ab", buffering=0)
        creationflags = 0
        start_new_session = os.name != "nt"
        if os.name == "nt":
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
        process = subprocess.Popen(
            argv,
            cwd=str(workdir) if workdir else None,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            shell=False,
            creationflags=creationflags,
            start_new_session=start_new_session,
        )
        log_handle.close()
        result = {"pid": process.pid, "command": command, "shell": shell, "cwd": str(workdir) if workdir else str(Path.cwd()), "log_path": str(log_path)}
        self._audit("start_process", {"command": command, "cwd": cwd, "shell": shell, "environment": environment or {}}, "ok", f"pid={process.pid}")
        return result

    def list_processes(self, name_filter: str = "", max_results: int = 300) -> dict[str, Any]:
        max_results = max(1, min(max_results, 5000))
        needle = name_filter.lower().strip()
        processes: list[dict[str, Any]] = []
        for process in psutil.process_iter(["pid", "ppid", "name", "username", "status", "create_time", "cmdline"]):
            try:
                info = process.info
                searchable = " ".join([str(info.get("name") or ""), " ".join(info.get("cmdline") or [])]).lower()
                if needle and needle not in searchable:
                    continue
                processes.append(
                    {
                        "pid": info.get("pid"),
                        "ppid": info.get("ppid"),
                        "name": info.get("name"),
                        "username": info.get("username"),
                        "status": info.get("status"),
                        "created": datetime.fromtimestamp(info["create_time"], timezone.utc).isoformat() if info.get("create_time") else None,
                        "command_line": info.get("cmdline") or [],
                    }
                )
            except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
                continue
            if len(processes) >= max_results:
                break
        result = {"filter": name_filter, "processes": processes, "truncated": len(processes) >= max_results}
        self._audit("list_processes", {"name_filter": name_filter, "max_results": max_results}, "ok", f"{len(processes)} processes")
        return result

    def terminate_process(self, pid: int, force: bool = False, include_children: bool = False) -> dict[str, Any]:
        if pid == os.getpid():
            raise ValueError("Refusing to terminate the MCP server itself")
        process = psutil.Process(pid)
        targets = process.children(recursive=True) if include_children else []
        targets.append(process)
        acted: list[int] = []
        for target in reversed(targets):
            try:
                target.kill() if force else target.terminate()
                acted.append(target.pid)
            except psutil.NoSuchProcess:
                continue
        wait_targets = []
        for item in acted:
            try:
                wait_targets.append(psutil.Process(item))
            except psutil.NoSuchProcess:
                continue
        gone, alive = psutil.wait_procs(wait_targets, timeout=5)
        result = {"requested_pid": pid, "force": force, "include_children": include_children, "signaled_pids": acted, "stopped_pids": [p.pid for p in gone], "still_alive_pids": [p.pid for p in alive]}
        self._audit("terminate_process", {"pid": pid, "force": force, "include_children": include_children}, "ok", json.dumps(result))
        return result
