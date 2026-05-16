"""Shell Agent — executes commands in the project workspace with live output streaming.

Design goals:
  - Streams stdout/stderr in real time so the user sees progress (tests, builds, servers)
  - Hard timeout with subprocess kill so a runaway process never hangs CodeMitra
  - Whitelisted executables (same _DEFAULT_COMMANDS as filesystem agent)
  - User sees a coloured "Shell Agent" panel with command, exit code, and truncated output
  - The main LLM gets the exit code + tail of output so it can react to failures
"""
from __future__ import annotations

import os
import inspect
import pathlib
import platform
import re
import shlex
import subprocess
import threading
import itertools
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from rich.console import Console, Group
from rich.panel import Panel
from rich.rule import Rule
from rich.text import Text

# ─── Allowed executables ──────────────────────────────────────────────────────

_DEFAULT_COMMANDS: set[str] = {
    "python", "python3", "pip", "pip3",
    "git", "npm", "node", "npx",
    "uvicorn", "gunicorn",
    "pytest", "ruff", "mypy", "black", "isort",
    "make", "cargo", "go",
    # read-only directory listing (safe on all platforms)
    "dir", "ls", "tree",
}

# ─── Config ───────────────────────────────────────────────────────────────────

@dataclass
class ShellConfig:
    root_workspace: str | None = None
    allowed_roots: list[str] = field(default_factory=list)
    current_cwd: str | None = None
    session_mode: str = "approve"
    allowed_commands: set[str] = field(default_factory=lambda: set(_DEFAULT_COMMANDS))
    default_timeout: int = 60          # seconds
    max_output_lines: int = 200        # lines kept in memory
    stream_to_console: bool = True     # print output live
    confirm_fn: Callable[..., str | None] | None = None  # (command, cwd) -> amended_command | None

_config = ShellConfig()
_background_tasks: dict[str, "BackgroundTask"] = {}
_background_lock = threading.Lock()
_background_counter = itertools.count(1)


def configure(
    workspace: str | None = None,
    allowed_roots: list[str] | None = None,
    session_mode: str = "approve",
    allowed_commands: set[str] | None = None,
    default_timeout: int = 60,
    max_output_lines: int = 200,
    stream_to_console: bool = True,
    confirm_fn: Callable[..., bool] | None = None,
) -> None:
    """Update the shell agent config for this session."""
    global _config
    resolved_workspace = pathlib.Path(workspace).resolve().__str__() if workspace else None
    _config = ShellConfig(
        root_workspace=resolved_workspace,
        allowed_roots=[str(pathlib.Path(root).resolve()) for root in (allowed_roots or [])],
        current_cwd=resolved_workspace,
        session_mode=session_mode,
        allowed_commands=allowed_commands if allowed_commands is not None else set(_DEFAULT_COMMANDS),
        default_timeout=default_timeout,
        max_output_lines=max_output_lines,
        stream_to_console=stream_to_console,
        confirm_fn=confirm_fn,
    )


# ─── Result ───────────────────────────────────────────────────────────────────

@dataclass
class ShellResult:
    command: str
    cwd: str
    exit_code: int
    output_lines: list[str]          # combined stdout+stderr, chronological
    timed_out: bool = False
    denied: bool = False             # user declined

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and not self.timed_out and not self.denied

    @property
    def output(self) -> str:
        return "\n".join(self.output_lines)

    @property
    def tail(self) -> str:
        """Last 30 lines — what the LLM receives."""
        return "\n".join(self.output_lines[-30:])

    def to_llm_summary(self) -> str:
        status = "OK" if self.ok else ("TIMEOUT" if self.timed_out else ("DENIED" if self.denied else "FAILED"))
        return (
            f"Command: {self.command}\n"
            f"CWD: {self.cwd}\n"
            f"Exit code: {self.exit_code}  [{status}]\n\n"
            f"Output (last 30 lines):\n{self.tail or '(no output)'}"
        )


@dataclass
class BackgroundTask:
    id: str
    command: str
    cwd: str
    status: str
    started_at: str
    completed_at: str | None = None
    exit_code: int | None = None
    output_lines: list[str] = field(default_factory=list)
    note: str = ""
    proc: subprocess.Popen | None = field(default=None, repr=False)
    watcher_thread: threading.Thread | None = field(default=None, repr=False)

    @property
    def tail(self) -> str:
        return "\n".join(self.output_lines[-30:])


def _now_stamp() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _task_snapshot(task: BackgroundTask) -> BackgroundTask:
    return BackgroundTask(
        id=task.id,
        command=task.command,
        cwd=task.cwd,
        status=task.status,
        started_at=task.started_at,
        completed_at=task.completed_at,
        exit_code=task.exit_code,
        output_lines=list(task.output_lines),
        note=task.note,
    )


def _trim_background_output(task: BackgroundTask) -> None:
    if len(task.output_lines) > _config.max_output_lines:
        task.output_lines[:] = task.output_lines[-_config.max_output_lines:]


# ─── Core runner ─────────────────────────────────────────────────────────────

def _resolve_cwd(cwd: str | None) -> str:
    """Resolve cwd: prefer current shell cwd, then explicit path, then os.getcwd()."""
    base = _config.current_cwd or _config.root_workspace or os.getcwd()
    if cwd and cwd not in (".", ""):
        p = pathlib.Path(cwd)
        if not p.is_absolute():
            p = pathlib.Path(base) / p
        return str(p.resolve())
    return str(pathlib.Path(base).resolve())


def get_cwd() -> str:
    """Return the current shell working directory for this session."""
    return _resolve_cwd(None)


def reset_background_tasks() -> None:
    """Stop and forget all tracked background tasks. Primarily for tests."""
    with _background_lock:
        task_ids = list(_background_tasks.keys())
    for task_id in task_ids:
        stop_background_task(task_id)
    with _background_lock:
        _background_tasks.clear()


def _check_path_in_workspace(path: pathlib.Path) -> str | None:
    roots = ([pathlib.Path(_config.root_workspace)] if _config.root_workspace else []) + [
        pathlib.Path(root) for root in _config.allowed_roots
    ]
    if not roots:
        return None
    resolved = path.resolve()
    for root in roots:
        try:
            resolved.relative_to(root.resolve())
            return None
        except ValueError:
            continue
    return f"Path is outside the workspace: {path}"


def _resolve_target_path(raw_path: str | None, cwd: str) -> pathlib.Path:
    if not raw_path or raw_path in (".", ""):
        return pathlib.Path(cwd)
    target = pathlib.Path(raw_path)
    if not target.is_absolute():
        target = pathlib.Path(cwd) / target
    return target.resolve()


def _split_command(command: str) -> list[str]:
    return shlex.split(command, posix=(platform.system() != "Windows"))


def _confirm_command(command: str, cwd: str) -> str | None:
    """Call confirm_fn and return the (possibly amended) command, or None if denied."""
    if _config.confirm_fn is None:
        return command
    params = list(inspect.signature(_config.confirm_fn).parameters.values())
    positional = [
        param for param in params
        if param.kind in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        )
    ]
    if any(param.kind == inspect.Parameter.VAR_POSITIONAL for param in params) or len(positional) >= 2:
        return _config.confirm_fn(command, cwd)
    return _config.confirm_fn(command)


def _background_worker(task_id: str) -> None:
    with _background_lock:
        task = _background_tasks.get(task_id)
        proc = task.proc if task else None

    if task is None or proc is None:
        return

    try:
        if proc.stdout is not None:
            for raw in proc.stdout:
                line = raw.rstrip("\n")
                with _background_lock:
                    current = _background_tasks.get(task_id)
                    if current is None:
                        break
                    current.output_lines.append(line)
                    _trim_background_output(current)
        proc.wait()
    except Exception as exc:
        with _background_lock:
            current = _background_tasks.get(task_id)
            if current is not None:
                current.output_lines.append(f"✗ Background task failed: {exc}")
                _trim_background_output(current)
    finally:
        exit_code = proc.returncode if proc.returncode is not None else 1
        with _background_lock:
            current = _background_tasks.get(task_id)
            if current is None:
                return
            current.exit_code = exit_code
            current.completed_at = current.completed_at or _now_stamp()
            current.proc = None
            current.watcher_thread = None
            if current.status == "stopped":
                return
            current.status = "completed" if exit_code == 0 else "failed"


def _validate_background_command(command: str, resolved_cwd: str) -> str | None:
    resolved_path = pathlib.Path(resolved_cwd)
    if err := _check_path_in_workspace(resolved_path):
        return f"✗ {err}"

    try:
        parts = _split_command(command)
    except ValueError:
        parts = []
    exe = parts[0].lower() if parts else ""
    if exe in {"cd", "pwd", "ls", "dir", "ll", "tree", "cat", "type"}:
        return "✗ Background tasks only support subprocess commands. Use `/run <cmd>` for built-in navigation or listing commands."

    if _config.session_mode in {"read-only", "plan"}:
        return (
            f"✗ Shell execution is disabled in `{_config.session_mode}` mode. "
            "Use `/mode approve` or `/mode auto` to run commands."
        )

    if err := _check_executable(command):
        return f"✗ Permission denied: {err}"

    if _config.confirm_fn is not None and _confirm_command(command, resolved_cwd) is None:
        return "✗ Skipped: user declined"

    return None


def start_background(command: str, cwd: str | None = None) -> tuple[BackgroundTask | None, str | None]:
    """Launch a long-running subprocess command in the background."""
    resolved_cwd = _resolve_cwd(cwd)
    error = _validate_background_command(command, resolved_cwd)
    if error:
        return None, error

    try:
        proc = subprocess.Popen(
            _split_command(command),
            cwd=resolved_cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError:
        return None, f"✗ Executable not found: {_split_command(command)[0]}"
    except Exception as exc:
        return None, f"✗ Failed to start process: {exc}"

    task = BackgroundTask(
        id=f"bg-{next(_background_counter)}",
        command=command,
        cwd=resolved_cwd,
        status="running",
        started_at=_now_stamp(),
        proc=proc,
    )
    watcher = threading.Thread(target=_background_worker, args=(task.id,), daemon=True)
    task.watcher_thread = watcher
    with _background_lock:
        _background_tasks[task.id] = task
    watcher.start()
    return _task_snapshot(task), None


def list_background_tasks() -> list[BackgroundTask]:
    """Return tracked background tasks in creation order."""
    with _background_lock:
        tasks = list(_background_tasks.values())
    tasks.sort(key=lambda task: int(task.id.split("-")[-1]))
    return [_task_snapshot(task) for task in tasks]


def get_background_task(task_id: str) -> BackgroundTask | None:
    """Return a snapshot of a specific background task."""
    with _background_lock:
        task = _background_tasks.get(task_id)
    return _task_snapshot(task) if task is not None else None


def count_background_tasks(*, only_running: bool = False) -> int:
    """Count tracked background tasks."""
    with _background_lock:
        tasks = list(_background_tasks.values())
    if only_running:
        tasks = [task for task in tasks if task.status == "running"]
    return len(tasks)


def stop_background_task(task_id: str) -> tuple[BackgroundTask | None, str | None]:
    """Stop a running background task."""
    with _background_lock:
        task = _background_tasks.get(task_id)
        proc = task.proc if task is not None else None
        if task is None:
            return None, f"No background task found for `{task_id}`."
        if task.status != "running" or proc is None:
            return _task_snapshot(task), None
        task.status = "stopped"
        task.completed_at = _now_stamp()
        task.note = "Stopped by user."
    try:
        proc.kill()
    except Exception as exc:
        return None, f"Could not stop `{task_id}`. {exc}"
    return get_background_task(task_id), None


def _check_executable(command: str) -> str | None:
    """Return error string if the executable is not in the whitelist, else None."""
    try:
        parts = _split_command(command)
    except ValueError:
        return "Could not parse command"
    if not parts:
        return "Empty command"
    exe = pathlib.Path(parts[0]).name
    # Strip .exe on Windows
    exe = re.sub(r"\.exe$", "", exe, flags=re.IGNORECASE)
    if exe not in _config.allowed_commands:
        return (
            f"'{exe}' is not in the allowed commands list. "
            f"Allowed: {sorted(_config.allowed_commands)}"
        )
    return None


def _render_dir_listing(cwd: str) -> list[str]:
    root = pathlib.Path(cwd)
    entries = sorted(root.iterdir(), key=lambda e: (e.is_file(), e.name.lower()))
    if not entries:
        return [f"{root.name or root} (empty)"]
    lines = [str(root)]
    for entry in entries:
        prefix = "[dir] " if entry.is_dir() else "[file]"
        lines.append(f"{prefix} {entry.name}")
    return lines


def _render_tree(cwd: str, max_depth: int = 4) -> list[str]:
    root = pathlib.Path(cwd)
    lines: list[str] = [root.name or str(root)]

    def walk(path: pathlib.Path, prefix: str, depth: int) -> None:
        if depth > max_depth:
            return
        entries = sorted(path.iterdir(), key=lambda e: (e.is_file(), e.name.lower()))
        for index, entry in enumerate(entries):
            connector = "└── " if index == len(entries) - 1 else "├── "
            lines.append(f"{prefix}{connector}{entry.name}")
            if entry.is_dir():
                walk(entry, prefix + ("    " if index == len(entries) - 1 else "│   "), depth + 1)

    walk(root, "", 1)
    return lines


def _read_text_file(path: pathlib.Path) -> list[str]:
    try:
        return path.read_text(encoding="utf-8").splitlines() or [""]
    except UnicodeDecodeError:
        return [f"✗ Cannot display binary file: {path.name}"]


def _run_builtin(command: str, cwd: str) -> ShellResult | None:
    try:
        parts = _split_command(command)
    except ValueError:
        return None
    if not parts:
        return None

    exe = parts[0].lower()
    arg = parts[1] if len(parts) > 1 else ""
    if exe == "cd":
        target = _resolve_target_path(arg, cwd)
        if err := _check_path_in_workspace(target):
            return ShellResult(command=command, cwd=cwd, exit_code=1, output_lines=[f"✗ {err}"])
        if not target.exists():
            return ShellResult(command=command, cwd=cwd, exit_code=1, output_lines=[f"✗ Directory not found: {arg or target}"])
        if not target.is_dir():
            return ShellResult(command=command, cwd=cwd, exit_code=1, output_lines=[f"✗ Not a directory: {arg or target}"])
        _config.current_cwd = str(target)
        return ShellResult(command=command, cwd=str(target), exit_code=0, output_lines=[str(target)])
    if exe == "pwd":
        return ShellResult(command=command, cwd=cwd, exit_code=0, output_lines=[cwd])
    if exe in {"ls", "dir", "ll"}:
        target = _resolve_target_path(arg, cwd)
        if err := _check_path_in_workspace(target):
            return ShellResult(command=command, cwd=cwd, exit_code=1, output_lines=[f"✗ {err}"])
        if not target.exists():
            return ShellResult(command=command, cwd=cwd, exit_code=1, output_lines=[f"✗ Path not found: {arg or target}"])
        if target.is_file():
            return ShellResult(command=command, cwd=str(target.parent), exit_code=0, output_lines=[str(target)])
        return ShellResult(command=command, cwd=str(target), exit_code=0, output_lines=_render_dir_listing(str(target)))
    if exe == "tree":
        target = _resolve_target_path(arg, cwd)
        if err := _check_path_in_workspace(target):
            return ShellResult(command=command, cwd=cwd, exit_code=1, output_lines=[f"✗ {err}"])
        if not target.exists():
            return ShellResult(command=command, cwd=cwd, exit_code=1, output_lines=[f"✗ Path not found: {arg or target}"])
        if target.is_file():
            return ShellResult(command=command, cwd=str(target.parent), exit_code=0, output_lines=[str(target)])
        return ShellResult(command=command, cwd=str(target), exit_code=0, output_lines=_render_tree(str(target)))
    if exe in {"cat", "type"}:
        target = _resolve_target_path(arg, cwd)
        if err := _check_path_in_workspace(target):
            return ShellResult(command=command, cwd=cwd, exit_code=1, output_lines=[f"✗ {err}"])
        if not target.exists():
            return ShellResult(command=command, cwd=cwd, exit_code=1, output_lines=[f"✗ File not found: {arg or target}"])
        if not target.is_file():
            return ShellResult(command=command, cwd=cwd, exit_code=1, output_lines=[f"✗ Not a file: {arg or target}"])
        return ShellResult(command=command, cwd=str(target.parent), exit_code=0, output_lines=_read_text_file(target))
    return None


def execute(
    command: str,
    cwd: str | None = None,
    timeout: int | None = None,
    console: Console | None = None,
) -> ShellResult:
    """
    Run *command* in *cwd*, stream output, and return a ShellResult.

    - Output is streamed line-by-line to *console* if provided and stream_to_console is True.
    - Process is killed after *timeout* seconds (default: _config.default_timeout).
    """
    resolved_cwd = _resolve_cwd(cwd)
    timeout = timeout if timeout is not None else _config.default_timeout

    resolved_path = pathlib.Path(resolved_cwd)
    if err := _check_path_in_workspace(resolved_path):
        return ShellResult(command=command, cwd=resolved_cwd, exit_code=1, output_lines=[f"✗ {err}"])

    builtin_result = _run_builtin(command, resolved_cwd)
    if builtin_result is not None:
        return builtin_result

    if _config.session_mode in {"read-only", "plan"}:
        return ShellResult(
            command=command,
            cwd=resolved_cwd,
            exit_code=1,
            output_lines=[
                f"✗ Shell execution is disabled in `{_config.session_mode}` mode. "
                "Use `/mode approve` or `/mode auto` to run commands."
            ],
        )

    # Permission check
    if err := _check_executable(command):
        return ShellResult(command=command, cwd=resolved_cwd, exit_code=1, output_lines=[f"✗ Permission denied: {err}"])

    # User confirmation — confirm_fn may return an amended command string or None (denied)
    if _config.confirm_fn is not None:
        approved_command = _confirm_command(command, resolved_cwd)
        if approved_command is None:
            return ShellResult(command=command, cwd=resolved_cwd, exit_code=1, output_lines=["Skipped: user declined"], denied=True)
        command = approved_command

    lines: list[str] = []
    proc: subprocess.Popen | None = None
    timed_out = False

    def _reader(stream, tag: str) -> None:
        """Read lines from a stream, print live, and append to lines list."""
        try:
            for raw in stream:
                line = raw.rstrip("\n")
                lines.append(line)
                if _config.stream_to_console and console is not None:
                    console.print(f"  [dim]{line}[/dim]")
                if len(lines) > _config.max_output_lines * 2:
                    lines[:] = lines[-_config.max_output_lines:]
        except Exception:
            pass

    try:
        proc = subprocess.Popen(
            _split_command(command),
            cwd=resolved_cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            encoding="utf-8",
            errors="replace",
        )
        t = threading.Thread(target=_reader, args=(proc.stdout, "out"), daemon=True)
        t.start()
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            t.join(timeout=2)
            timed_out = True
        t.join(timeout=5)
        exit_code = proc.returncode if proc.returncode is not None else 1

    except FileNotFoundError:
        lines.append(f"✗ Executable not found: {_split_command(command)[0]}")
        exit_code = 1
    except Exception as exc:
        lines.append(f"✗ Failed to start process: {exc}")
        exit_code = 1

    # Trim to max_output_lines
    kept = lines[-_config.max_output_lines:]
    return ShellResult(
        command=command,
        cwd=resolved_cwd,
        exit_code=exit_code,
        output_lines=kept,
        timed_out=timed_out,
    )


# ─── LangChain tool ──────────────────────────────────────────────────────────

@tool
def run_shell(command: str, cwd: str = "", timeout: int = 60) -> str:
    """
    Run a shell command in the project workspace and return the output + exit code.
    Use for: running scripts, tests, linters, installs, or any terminal command.
    cwd: working directory relative to the project root (empty = project root).
    timeout: seconds before the process is killed (default 60).
    """
    result = execute(command, cwd=cwd or None, timeout=timeout)
    return result.to_llm_summary()


# ─── Agent loop (for direct invocation) ──────────────────────────────────────

_SYSTEM_PROMPT = """You are the Shell Agent inside CodeMitra.

Your job is to run terminal commands on behalf of the user inside their project workspace.

## Rules
1. Use run_shell for every command — never describe commands without running them.
2. Always use the project root as cwd unless the user specifies otherwise.
3. If a command fails (non-zero exit), read the output and suggest a fix before running again.
4. Never run destructive commands (rm -rf, format, drop database) without explicit user instruction.
5. Final reply must be plain English only — no JSON, no tool syntax.
"""


def run_agent(llm, user_request: str, console: Console | None = None) -> str:
    """Run the shell agent with the LLM and return a plain text summary."""
    llm_with_tools = llm.bind_tools([run_shell])
    messages: list = [
        SystemMessage(content=_SYSTEM_PROMPT),
        HumanMessage(content=user_request),
    ]

    summary = ""
    while True:
        phase = "Summarizing command results..." if any(isinstance(m, ToolMessage) for m in messages) else "Planning command execution..."
        if console is not None:
            with console.status(f"[bold blue]{phase}[/bold blue]", spinner="dots"):
                response: AIMessage = llm_with_tools.invoke(messages)
        else:
            response = llm_with_tools.invoke(messages)
        messages.append(response)

        if not response.tool_calls:
            summary = response.content.strip()
            break

        for tc in response.tool_calls:
            args = tc["args"]
            result = execute(
                command=args.get("command", ""),
                cwd=args.get("cwd") or None,
                timeout=args.get("timeout", _config.default_timeout),
                console=console,
            )
            messages.append(ToolMessage(content=result.to_llm_summary(), tool_call_id=tc["id"]))

    return summary


# ─── Routing tool (called by the main LLM) ───────────────────────────────────

def make_routing_tool(llm, console: Console | None = None):
    """Return a LangChain tool the main LLM can call to run shell commands."""
    @tool
    def run_command(request: str) -> str:
        """
        Run a terminal command or script in the current project.
        Use when the user asks to run, execute, test, lint, or start something.
        Pass the full user request unchanged.
        """
        return run_agent(llm, request, console=console)
    return run_command


# ─── Rich renderer ───────────────────────────────────────────────────────────

def render(result: ShellResult) -> Panel:
    """Build a Rich Panel showing the shell result."""
    parts: list = []

    # Command line
    parts.append(Text.from_markup("[dim]Run[/dim]"))
    parts.append(Text(result.command, style="bold"))
    if result.cwd:
        parts.append(Text.from_markup(f"[dim]CWD: {result.cwd}[/dim]"))
    parts.append(Text(""))

    # Output
    if result.output_lines:
        parts.append(Rule(title="tail", style="dim green", align="left"))
        parts.append(Text(""))
        # Show last 40 lines in the panel (full output was already streamed live)
        for line in result.output_lines[-40:]:
            parts.append(Text(line, style="dim"))
        parts.append(Text(""))

    # Footer
    if result.denied:
        status_text = Text("Skipped - user declined", style="bold yellow")
    elif result.timed_out:
        status_text = Text("Timed out", style="bold red")
    elif result.ok:
        status_text = Text(f"Completed - exit {result.exit_code}", style="bold green")
    else:
        status_text = Text(f"Failed - exit {result.exit_code}", style="bold red")

    parts.append(status_text)

    return Panel(
        Group(*parts),
        title="[bold green]Run[/bold green]",
        border_style="green",
        padding=(1, 2),
    )
