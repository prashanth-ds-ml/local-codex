from __future__ import annotations

import pathlib
import platform
import re
import shlex
import shutil
import subprocess

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool

from app.agents.response import AgentResponse, ToolResult
from app import memory

# ─── Permissions ──────────────────────────────────────────────────────────────

# Safe tools enabled by default.
_DEFAULT_TOOLS: set[str] = {
    "create_folder",
    "create_file",
    "read_file",
    "list_directory",
    "delete_file",
    "delete_folder",
    "move_file",
    "create_venv",
    "install_packages",
    "git_status",
    "git_diff",
    "git_commit",
}

# Tools that modify or destroy existing content — require user confirmation.
_DESTRUCTIVE_TOOLS: set[str] = {
    "delete_file",
    "delete_folder",
    "move_file",
}

_WRITE_PREVIEW_TOOLS: set[str] = {
    "create_file",
}

# Executables allowed when run_command is enabled.
_DEFAULT_COMMANDS: set[str] = {
    "python", "python3", "pip", "pip3",
    "git", "npm", "node", "uvicorn",
}


class PermissionGuard:
    """
    Controls what the filesystem agent is allowed to do.

    workspace       – if set, all path arguments must live inside this directory.
    allowed_tools   – set of tool names the agent may call.
    allowed_commands– executables permitted when run_command is enabled.
    """

    def __init__(
        self,
        workspace: str | None = None,
        allowed_roots: list[str] | None = None,
        allowed_tools: set[str] | None = None,
        allowed_commands: set[str] | None = None,
        confirm_fn=None,
        require_diff_approval: bool = False,
    ) -> None:
        self.workspace = pathlib.Path(workspace).resolve() if workspace else None
        self.allowed_roots = [pathlib.Path(root).resolve() for root in (allowed_roots or [])]
        self.allowed_tools = allowed_tools if allowed_tools is not None else set(_DEFAULT_TOOLS)
        self.allowed_commands = allowed_commands if allowed_commands is not None else set(_DEFAULT_COMMANDS)
        # Callable(tool_name, args_dict) -> bool. None = auto-approve (no TTY).
        self.confirm_fn = confirm_fn
        self.require_diff_approval = require_diff_approval

    # ── Checks ────────────────────────────────────────────────────────────────

    def check_path(self, *paths: str) -> str | None:
        """Return an error string if any path escapes the workspace, else None."""
        if self.workspace is None and not self.allowed_roots:
            return None
        for p in paths:
            resolved = _resolve_path(p)
            roots = ([self.workspace] if self.workspace else []) + self.allowed_roots
            if not any(_is_relative_to(resolved, root) for root in roots):
                return f"✗ Permission denied: '{p}' is outside the allowed roots"
        return None

    def check_command(self, command: str) -> str | None:
        """Return an error string if the executable is not whitelisted, else None."""
        try:
            parts = shlex.split(command)
        except ValueError:
            return "✗ Could not parse command"
        if not parts:
            return "✗ Empty command"
        exe = pathlib.Path(parts[0]).name
        if exe not in self.allowed_commands:
            return (
                f"✗ Permission denied: '{exe}' is not in the allowed commands list. "
                f"Allowed: {sorted(self.allowed_commands)}"
            )
        return None

    def filter_tools(self, tools: list) -> list:
        """Return only the tools whose names are in allowed_tools."""
        return [t for t in tools if t.name in self.allowed_tools]


# Module-level guard — replace with configure() to change settings.
_guard = PermissionGuard()
_active_change_set: list[dict] | None = None


def configure(
    workspace: str | None = None,
    allowed_roots: list[str] | None = None,
    allowed_tools: set[str] | None = None,
    allowed_commands: set[str] | None = None,
    confirm_fn=None,
    require_diff_approval: bool = False,
) -> None:
    """
    Update the permission guard for this session.

    Examples
    --------
    # Lock agent to a specific project folder
    filesystem.configure(workspace="C:/Users/prash/projects/myapi")

    # Also allow destructive tools
    filesystem.configure(
        workspace="C:/Users/prash/projects/myapi",
        allowed_tools=filesystem._DEFAULT_TOOLS | {"delete_file", "run_command"},
    )
    """
    global _guard
    _guard = PermissionGuard(
        workspace=workspace,
        allowed_roots=allowed_roots,
        allowed_tools=allowed_tools,
        allowed_commands=allowed_commands,
        confirm_fn=confirm_fn,
        require_diff_approval=require_diff_approval,
    )


# ─── System prompt ────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """You are the Filesystem Setup Agent inside CodeMitra.

## Available tools
- create_folder    : create directories (including nested paths)
- create_file      : create text files with optional content
- read_file        : read the contents of an existing file
- list_directory   : list files and folders at a path
- delete_file      : delete a single file
- delete_folder    : delete a folder and all its contents recursively
- move_file        : move or rename a file or folder
- create_venv      : create a Python .venv in a project directory
- install_packages : install pip packages into .venv, or from requirements.txt
- run_command      : run a whitelisted shell command in a given directory
- git_status       : show working tree status (short format)
- git_diff         : show unstaged or staged diff
- git_commit       : stage all changes and create a commit

Note: you will only receive the tools that are currently permitted.
Do not attempt operations outside your available tools.

## Workflow rules
1. Always create the project root folder before anything else.
2. Create sub-folders and files before setting up the environment.
3. Create the .venv before installing any packages.
4. The current workspace is the default project folder. If the user says "same folder", "current folder", or "here", use the current workspace instead of asking for a path again.
5. If packages are needed but no requirements.txt exists and none were named, ask.
6. Before deleting or overwriting anything, confirm with the user.
7. Do not call list_directory before every simple action. Use it only when you need missing context.
8. For rename requests, rename only the exact file or folder the user named. Do not rename nested package folders unless the user explicitly asked for that too.
9. If any tool step fails, acknowledge the failure plainly instead of claiming the whole task succeeded.

## Output rules
- Use the tools — never describe steps without executing them.
- Final reply must be plain English only. No JSON, no code blocks, no tool names.
"""


# ─── Tools ────────────────────────────────────────────────────────────────────

@tool
def create_folder(path: str) -> str:
    """Create a directory and any missing parent directories at the given path."""
    if err := _guard.check_path(path):
        return err
    try:
        _resolve_path(path).mkdir(parents=True, exist_ok=True)
        return f"✓ Created folder: {path}"
    except Exception as exc:
        return f"✗ create_folder failed: {exc}"


@tool
def create_file(path: str, content: str = "") -> str:
    """Create a file at path with optional text content. Parent directories are created automatically."""
    if err := _guard.check_path(path):
        return err
    try:
        p = _resolve_path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        existed = p.exists() and p.is_file()
        previous = None
        if p.exists() and p.is_file():
            previous = p.read_text(encoding="utf-8")
            if previous == content:
                return f"✓ File unchanged: {path}"
        p.write_text(content, encoding="utf-8")
        _record_change({
            "kind": "create_file",
            "path": str(p),
            "existed": existed,
            "before": previous,
            "after": content,
        })
        return f"✓ Created file: {path}"
    except Exception as exc:
        return f"✗ create_file failed: {exc}"


def _safe_is_dir(path: pathlib.Path) -> bool:
    try:
        return path.is_dir()
    except OSError:
        return False


def _safe_is_file(path: pathlib.Path) -> bool:
    try:
        return path.is_file()
    except OSError:
        return False


def _resolve_path(path: str | None) -> pathlib.Path:
    target = pathlib.Path(path or ".")
    if not target.is_absolute() and _guard.workspace is not None:
        target = _guard.workspace / target
    return target.resolve()


def _is_relative_to(path: pathlib.Path, root: pathlib.Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


@tool
def read_file(path: str) -> str:
    """Read and return the full text content of a file."""
    if err := _guard.check_path(path):
        return err
    try:
        return _resolve_path(path).read_text(encoding="utf-8")
    except Exception as exc:
        return f"✗ read_file failed: {exc}"


@tool
def list_directory(path: str = ".") -> str:
    """List all files and sub-folders inside a directory."""
    if err := _guard.check_path(path):
        return err
    try:
        p = _resolve_path(path)
        entries = sorted(
            p.iterdir(),
            key=lambda e: (_safe_is_file(e), e.name.lower()),
        )
        if not entries:
            return f"{path}/ (empty)"
        lines = [
            f"  {'[dir] ' if _safe_is_dir(e) else '[file]'} {e.name}"
            for e in entries
        ]
        return f"{path}/\n" + "\n".join(lines)
    except Exception as exc:
        return f"✗ list_directory failed: {exc}"


@tool
def delete_file(path: str) -> str:
    """Delete a single file at the given path."""
    if err := _guard.check_path(path):
        return err
    if _guard.confirm_fn and not _guard.confirm_fn("delete_file", {"path": path}):
        return "✗ Skipped: user declined delete_file"
    try:
        target = _resolve_path(path)
        existed = target.exists()
        previous = None
        if existed:
            try:
                previous = target.read_text(encoding="utf-8")
            except Exception:
                _record_change({
                    "kind": "delete_file",
                    "path": str(target),
                    "undo_supported": False,
                    "reason": "The deleted file could not be captured as UTF-8 text.",
                })
                target.unlink(missing_ok=True)
                return f"✓ Deleted file: {path}"
        target.unlink(missing_ok=True)
        if existed:
            _record_change({
                "kind": "delete_file",
                "path": str(target),
                "undo_supported": True,
                "before": previous,
            })
        return f"✓ Deleted file: {path}"
    except Exception as exc:
        return f"✗ delete_file failed: {exc}"


@tool
def delete_folder(path: str) -> str:
    """Delete a folder and all its contents recursively."""
    if err := _guard.check_path(path):
        return err
    if _guard.confirm_fn and not _guard.confirm_fn("delete_folder", {"path": path}):
        return "✗ Skipped: user declined delete_folder"
    try:
        _record_change({
            "kind": "delete_folder",
            "path": str(_resolve_path(path)),
            "undo_supported": False,
            "reason": "Folder deletions are not undoable yet.",
        })
        shutil.rmtree(_resolve_path(path))
        return f"✓ Deleted folder: {path}"
    except Exception as exc:
        return f"✗ delete_folder failed: {exc}"


@tool
def move_file(src: str, dest: str) -> str:
    """Move or rename a file or folder from src to dest."""
    if err := _guard.check_path(src, dest):
        return err
    if _guard.confirm_fn and not _guard.confirm_fn("move_file", {"src": src, "dest": dest}):
        return "✗ Skipped: user declined move_file"
    try:
        source = _resolve_path(src)
        destination = _resolve_path(dest)
        if not source.exists():
            return f"✗ move_file failed: source does not exist: {src}"
        if destination.exists():
            return f"✗ move_file failed: destination already exists: {dest}"
        _record_change({
            "kind": "move_file",
            "src": str(source),
            "dest": str(destination),
            "is_dir": source.is_dir(),
        })
        shutil.move(str(source), str(destination))
        return f"✓ Moved '{src}' → '{dest}'"
    except Exception as exc:
        return f"✗ move_file failed: {exc}"


@tool
def create_venv(project_path: str) -> str:
    """Create a Python virtual environment (.venv) inside the given project directory."""
    if err := _guard.check_path(project_path):
        return err
    try:
        project_dir = _resolve_path(project_path)
        result = subprocess.run(
            ["python", "-m", "venv", ".venv"],
            cwd=project_dir,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return f"✗ create_venv failed: {result.stderr.strip()}"
        return f"✓ Created .venv in {project_path}"
    except Exception as exc:
        return f"✗ create_venv failed: {exc}"


@tool
def install_packages(project_path: str, packages: list[str] | None = None) -> str:
    """
    Install packages into the project's .venv.
    If packages is omitted or empty, installs from requirements.txt in project_path.
    If packages are given, installs them and writes the pinned result to requirements.txt.
    """
    if err := _guard.check_path(project_path):
        return err
    try:
        project_dir = _resolve_path(project_path)
        pip = _pip(str(project_dir))
        if packages:
            result = subprocess.run(
                [pip, "install", *packages],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                return f"✗ install failed: {result.stderr.strip()}"
            freeze = subprocess.run([pip, "freeze"], capture_output=True, text=True)
            (project_dir / "requirements.txt").write_text(
                freeze.stdout, encoding="utf-8"
            )
            return f"✓ Installed {', '.join(packages)} and wrote requirements.txt"
        else:
            req = project_dir / "requirements.txt"
            if not req.exists():
                return "✗ No requirements.txt found and no packages specified."
            result = subprocess.run(
                [pip, "install", "-r", str(req)],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                return f"✗ install failed: {result.stderr.strip()}"
            return "✓ Installed all packages from requirements.txt"
    except Exception as exc:
        return f"✗ install_packages failed: {exc}"


@tool
def run_command(command: str, cwd: str = ".") -> str:
    """
    Run a whitelisted shell command in the given working directory.
    Only executables in the allowed_commands list are permitted.
    """
    if err := _guard.check_path(cwd):
        return err
    if err := _guard.check_command(command):
        return err
    try:
        resolved_cwd = _resolve_path(cwd)
        result = subprocess.run(
            shlex.split(command),
            cwd=resolved_cwd,
            capture_output=True,
            text=True,
            timeout=120,
        )
        output = (result.stdout + result.stderr).strip()
        status = "✓" if result.returncode == 0 else "✗"
        return f"{status} [{result.returncode}]\n{output}" if output else f"{status} Done"
    except subprocess.TimeoutExpired:
        return "✗ Command timed out after 120 seconds"
    except Exception as exc:
        return f"✗ run_command failed: {exc}"


# ─── Git tools ───────────────────────────────────────────────────────────────

@tool
def git_status(cwd: str = ".") -> str:
    """Show the git working tree status (short format) for a repository."""
    if err := _guard.check_path(cwd):
        return err
    try:
        resolved_cwd = _resolve_path(cwd)
        result = subprocess.run(
            ["git", "status", "--short", "--branch"],
            cwd=resolved_cwd, capture_output=True, text=True,
        )
        output = result.stdout.strip() or "(nothing to report)"
        return f"✓ git status\n{output}" if result.returncode == 0 else f"✗ {result.stderr.strip()}"
    except Exception as exc:
        return f"✗ git_status failed: {exc}"


@tool
def git_diff(cwd: str = ".", staged: bool = False) -> str:
    """Show the diff of unstaged changes (staged=False) or staged changes (staged=True)."""
    if err := _guard.check_path(cwd):
        return err
    try:
        resolved_cwd = _resolve_path(cwd)
        args = ["git", "diff"]
        if staged:
            args.append("--staged")
        result = subprocess.run(args, cwd=resolved_cwd, capture_output=True, text=True)
        output = result.stdout.strip() or "(no diff)"
        return f"✓ git diff\n{output}" if result.returncode == 0 else f"✗ {result.stderr.strip()}"
    except Exception as exc:
        return f"✗ git_diff failed: {exc}"


@tool
def git_commit(cwd: str, message: str) -> str:
    """Stage all changes (git add -A) and create a commit with the given message."""
    if err := _guard.check_path(cwd):
        return err
    try:
        resolved_cwd = _resolve_path(cwd)
        add = subprocess.run(["git", "add", "-A"], cwd=resolved_cwd, capture_output=True, text=True)
        if add.returncode != 0:
            return f"✗ git add failed: {add.stderr.strip()}"
        commit = subprocess.run(
            ["git", "commit", "-m", message],
            cwd=resolved_cwd, capture_output=True, text=True,
        )
        output = commit.stdout.strip() or commit.stderr.strip()
        return f"✓ Committed: {message}\n{output}" if commit.returncode == 0 else f"✗ {output}"
    except Exception as exc:
        return f"✗ git_commit failed: {exc}"


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _pip(project_path: str) -> str:
    p = pathlib.Path(project_path)
    if platform.system() == "Windows":
        return str(p / ".venv" / "Scripts" / "pip")
    return str(p / ".venv" / "bin" / "pip")


def _clean(text: str) -> str:
    """Strip JSON tool-call blocks the model sometimes echoes in its final reply."""
    text = re.sub(r'\{[^{}]*"name"\s*:[^{}]*\}', "", text, flags=re.DOTALL)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _augment_request_with_workspace(user_request: str) -> str:
    """Attach explicit workspace guidance for path-light requests."""
    if _guard.workspace is None:
        return user_request

    normalized = user_request.lower()
    hints: list[str] = []
    if any(phrase in normalized for phrase in ("same folder", "current folder", "this folder", "here")):
        hints.append(f"Use the current workspace as the target path: {_guard.workspace}")
    if any(phrase in normalized for phrase in (".venv", "venv", "virtual environment")):
        hints.append("If you need a project path, use '.' which refers to the current workspace.")

    if not hints:
        return user_request
    joined = "\n".join(f"- {hint}" for hint in hints)
    return f"{user_request}\n\nExecution notes:\n{joined}"


def _first_error_text(agent_response: AgentResponse) -> str:
    for step in agent_response.steps:
        if not step.ok:
            return step.output.lstrip("✗").strip().splitlines()[0]
    return ""


def _finalize_summary(agent_response: AgentResponse, model_summary: str) -> str:
    """Prefer deterministic summaries whenever tool execution had any failures."""
    if agent_response.err_count == 0:
        return model_summary

    first_error = _first_error_text(agent_response)
    if agent_response.ok_count == 0:
        if first_error:
            return f"Could not complete the request. {first_error}."
        return "Could not complete the request."

    success_labels = [step.label for step in agent_response.steps if step.ok][:2]
    completed = ", ".join(label for label in success_labels if label) or f"{agent_response.ok_count} step(s)"
    if first_error:
        return (
            f"Completed {completed}, but hit {agent_response.err_count} error"
            f"{'s' if agent_response.err_count != 1 else ''}. {first_error}."
        )
    return (
        f"Completed {completed}, but hit {agent_response.err_count} error"
        f"{'s' if agent_response.err_count != 1 else ''}."
    )


def _record_change(entry: dict) -> None:
    global _active_change_set
    if _active_change_set is not None:
        _active_change_set.append(entry)


def _persist_active_change_set() -> None:
    global _active_change_set
    if not _active_change_set or _guard.workspace is None:
        _active_change_set = None
        return
    memory.record_last_change_set(
        str(_guard.workspace),
        {"entries": _active_change_set},
    )
    _active_change_set = None


def _discard_active_change_set() -> None:
    global _active_change_set
    _active_change_set = None


def undo_last_change_set(workspace: str) -> str:
    """Undo the last persisted create/move/delete file change set for this workspace."""
    change_set = memory.load_last_change_set(workspace)
    if not change_set:
        return "No undoable change set is available yet."

    entries = change_set.get("entries") or []
    unsupported = [
        entry for entry in entries
        if entry.get("undo_supported") is False
    ]
    if unsupported:
        reasons = "; ".join(entry.get("reason", "unsupported operation") for entry in unsupported[:2])
        return f"Cannot undo the last change set safely. {reasons}"

    try:
        for entry in reversed(entries):
            kind = entry.get("kind")
            if kind == "create_file":
                target = pathlib.Path(entry["path"])
                if entry.get("existed"):
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(entry.get("before") or "", encoding="utf-8")
                elif target.exists():
                    target.unlink()
            elif kind == "delete_file":
                target = pathlib.Path(entry["path"])
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(entry.get("before") or "", encoding="utf-8")
            elif kind == "move_file":
                src = pathlib.Path(entry["src"])
                dest = pathlib.Path(entry["dest"])
                if not dest.exists():
                    return f"Cannot undo the last rename because `{dest}` no longer exists."
                src.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(dest), str(src))
        memory.clear_last_change_set(workspace)
        return f"Undid {len(entries)} change step{'s' if len(entries) != 1 else ''} from the last change set."
    except Exception as exc:
        return f"Undo failed: {exc}"


def execute_cleanup(paths: list[str], request: str = "Apply approved cleanup plan") -> AgentResponse:
    """Delete a pre-approved list of files/folders with one approval handled upstream."""
    response = AgentResponse(request=request)
    saved_confirm = _guard.confirm_fn
    global _active_change_set
    _active_change_set = []
    _guard.confirm_fn = None
    try:
        for path in paths:
            target = _resolve_path(path)
            if target.is_dir():
                output = delete_folder.invoke({"path": path})
                tool_name = "delete_folder"
            else:
                output = delete_file.invoke({"path": path})
                tool_name = "delete_file"
            response.steps.append(ToolResult(tool=tool_name, args={"path": path}, output=str(output)))
        response.summary = _finalize_summary(
            response,
            f"Removed {response.ok_count} cleanup item{'s' if response.ok_count != 1 else ''}.",
        )
        _persist_active_change_set()
        return response
    finally:
        _discard_active_change_set()
        _guard.confirm_fn = saved_confirm


def _should_confirm_write(tool_name: str, args: dict) -> bool:
    """Return True when a write tool should show a diff preview before execution."""
    if tool_name not in _WRITE_PREVIEW_TOOLS or not _guard.require_diff_approval:
        return False

    path = args.get("path")
    if not path or _guard.check_path(path):
        return False

    target = pathlib.Path(path)
    if not target.exists() or not target.is_file():
        return False

    try:
        existing = target.read_text(encoding="utf-8")
    except Exception:
        return True

    return existing != args.get("content", "")


# ─── All tools (unfiltered) ───────────────────────────────────────────────────

_ALL_TOOLS = [
    create_folder,
    create_file,
    read_file,
    list_directory,
    delete_file,
    delete_folder,
    move_file,
    create_venv,
    install_packages,
    run_command,
    git_status,
    git_diff,
    git_commit,
]


# ─── Public API ───────────────────────────────────────────────────────────────

def make_routing_tool(llm):
    """Return a LangChain tool that the main LLM can call to invoke this agent."""
    @tool
    def setup_project(request: str) -> str:
        """
        Set up a Python project on disk. Use when the user asks to create folders,
        create files, create a virtual environment (.venv), or install Python packages.
        Pass the full user request unchanged.
        """
        return run(llm, request).summary
    return setup_project


def run(llm, user_request: str, console=None) -> AgentResponse:
    """Run the filesystem agent and return a structured AgentResponse."""
    active_tools = _guard.filter_tools(_ALL_TOOLS)
    tool_map = {t.name: t for t in active_tools}
    llm_with_tools = llm.bind_tools(active_tools)

    agent_response = AgentResponse(request=user_request)

    messages: list = [
        SystemMessage(content=_SYSTEM_PROMPT),
        HumanMessage(content=_augment_request_with_workspace(user_request)),
    ]

    global _active_change_set
    _active_change_set = []
    try:
        while True:
            phase = "Summarizing file changes..." if any(isinstance(m, ToolMessage) for m in messages) else "Planning file changes..."
            if console is not None:
                with console.status(f"[bold cyan]{phase}[/bold cyan]", spinner="dots"):
                    response: AIMessage = llm_with_tools.invoke(messages)
            else:
                response = llm_with_tools.invoke(messages)

            # Accumulate token usage
            meta = getattr(response, "usage_metadata", None) or {}
            agent_response.tokens_in += meta.get("input_tokens", 0)
            agent_response.tokens_out += meta.get("output_tokens", 0)

            messages.append(response)

            if not response.tool_calls:
                agent_response.summary = _finalize_summary(agent_response, _clean(response.content))
                _persist_active_change_set()
                return agent_response

            for tc in response.tool_calls:
                # Show live progress
                if console is not None:
                    args_str = ", ".join(
                        f"{k}={repr(str(v))[:50]}" for k, v in tc["args"].items()
                    )
                    console.print(
                        f"  [dim cyan]⋯[/dim cyan] [cyan]{tc['name']}[/cyan][dim]({args_str})[/dim]"
                    )

                fn = tool_map.get(tc["name"])
                if fn is None:
                    output = f"✗ Unknown tool: {tc['name']}"
                elif _guard.confirm_fn is not None and _should_confirm_write(tc["name"], tc["args"]):
                    approved = _guard.confirm_fn(tc["name"], tc["args"])
                    if approved:
                        if console is not None:
                            with console.status(f"[bold cyan]Running {tc['name']}...[/bold cyan]", spinner="dots"):
                                output = fn.invoke(tc["args"])
                        else:
                            output = fn.invoke(tc["args"])
                    else:
                        output = f"✗ Skipped: user declined {tc['name']}"
                else:
                    if console is not None:
                        with console.status(f"[bold cyan]Running {tc['name']}...[/bold cyan]", spinner="dots"):
                            output = fn.invoke(tc["args"])
                    else:
                        output = fn.invoke(tc["args"])
                agent_response.steps.append(
                    ToolResult(tool=tc["name"], args=tc["args"], output=str(output))
                )
                messages.append(ToolMessage(content=str(output), tool_call_id=tc["id"]))
    finally:
        _discard_active_change_set()
