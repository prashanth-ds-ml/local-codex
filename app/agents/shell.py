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
import pathlib
import platform
import re
import shlex
import subprocess
import threading
from dataclasses import dataclass, field
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
    workspace: str | None = None
    allowed_commands: set[str] = field(default_factory=lambda: set(_DEFAULT_COMMANDS))
    default_timeout: int = 60          # seconds
    max_output_lines: int = 200        # lines kept in memory
    stream_to_console: bool = True     # print output live
    confirm_fn: Callable[[str], bool] | None = None  # (command) -> bool

_config = ShellConfig()


def configure(
    workspace: str | None = None,
    allowed_commands: set[str] | None = None,
    default_timeout: int = 60,
    max_output_lines: int = 200,
    stream_to_console: bool = True,
    confirm_fn: Callable[[str], bool] | None = None,
) -> None:
    """Update the shell agent config for this session."""
    global _config
    _config = ShellConfig(
        workspace=pathlib.Path(workspace).resolve().__str__() if workspace else None,
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


# ─── Core runner ─────────────────────────────────────────────────────────────

def _resolve_cwd(cwd: str | None) -> str:
    """Resolve cwd: prefer config workspace, then given path, then os.getcwd()."""
    if cwd and cwd not in (".", ""):
        p = pathlib.Path(cwd)
        if not p.is_absolute() and _config.workspace:
            p = pathlib.Path(_config.workspace) / p
        return str(p.resolve())
    return _config.workspace or os.getcwd()


def _check_executable(command: str) -> str | None:
    """Return error string if the executable is not in the whitelist, else None."""
    try:
        parts = shlex.split(command)
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

    # Permission check
    if err := _check_executable(command):
        return ShellResult(command=command, cwd=resolved_cwd, exit_code=1, output_lines=[f"✗ Permission denied: {err}"])

    # User confirmation
    if _config.confirm_fn is not None:
        approved = _config.confirm_fn(command)
        if not approved:
            return ShellResult(command=command, cwd=resolved_cwd, exit_code=1, output_lines=["Skipped: user declined"], denied=True)

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
            shlex.split(command),
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
        lines.append(f"✗ Executable not found: {shlex.split(command)[0]}")
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
        response: AIMessage = llm_with_tools.invoke(messages)
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
    parts.append(Text.from_markup(f"[dim]$[/dim] [bold]{result.command}[/bold]"))
    if result.cwd:
        parts.append(Text.from_markup(f"[dim]  in {result.cwd}[/dim]"))
    parts.append(Text(""))

    # Output
    if result.output_lines:
        parts.append(Rule(title="output", style="dim green", align="left"))
        parts.append(Text(""))
        # Show last 40 lines in the panel (full output was already streamed live)
        for line in result.output_lines[-40:]:
            parts.append(Text(line, style="dim"))
        parts.append(Text(""))

    # Footer
    if result.denied:
        status_text = Text("  ✘ Skipped — user declined", style="bold yellow")
    elif result.timed_out:
        status_text = Text("  ✘ Timed out", style="bold red")
    elif result.ok:
        status_text = Text(f"  ✔ Exit {result.exit_code}", style="bold green")
    else:
        status_text = Text(f"  ✘ Exit {result.exit_code}", style="bold red")

    parts.append(status_text)

    return Panel(
        Group(*parts),
        title="[bold green]Shell Agent[/bold green]",
        border_style="green",
        padding=(1, 2),
    )
