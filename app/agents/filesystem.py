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

# ─── Permissions ──────────────────────────────────────────────────────────────

# Safe tools enabled by default. Destructive / shell tools are opt-in.
_DEFAULT_TOOLS: set[str] = {
    "create_folder",
    "create_file",
    "read_file",
    "list_directory",
    "create_venv",
    "install_packages",
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
        allowed_tools: set[str] | None = None,
        allowed_commands: set[str] | None = None,
    ) -> None:
        self.workspace = pathlib.Path(workspace).resolve() if workspace else None
        self.allowed_tools = allowed_tools if allowed_tools is not None else set(_DEFAULT_TOOLS)
        self.allowed_commands = allowed_commands if allowed_commands is not None else set(_DEFAULT_COMMANDS)

    # ── Checks ────────────────────────────────────────────────────────────────

    def check_path(self, *paths: str) -> str | None:
        """Return an error string if any path escapes the workspace, else None."""
        if self.workspace is None:
            return None
        for p in paths:
            try:
                pathlib.Path(p).resolve().relative_to(self.workspace)
            except ValueError:
                return f"✗ Permission denied: '{p}' is outside workspace '{self.workspace}'"
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


def configure(
    workspace: str | None = None,
    allowed_tools: set[str] | None = None,
    allowed_commands: set[str] | None = None,
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
        allowed_tools=allowed_tools,
        allowed_commands=allowed_commands,
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

Note: you will only receive the tools that are currently permitted.
Do not attempt operations outside your available tools.

## Workflow rules
1. Always create the project root folder before anything else.
2. Create sub-folders and files before setting up the environment.
3. Create the .venv before installing any packages.
4. If the user has not supplied a project path, ask for one first.
5. If packages are needed but no requirements.txt exists and none were named, ask.
6. Before deleting or overwriting anything, confirm with the user.

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
        pathlib.Path(path).mkdir(parents=True, exist_ok=True)
        return f"✓ Created folder: {path}"
    except Exception as exc:
        return f"✗ create_folder failed: {exc}"


@tool
def create_file(path: str, content: str = "") -> str:
    """Create a file at path with optional text content. Parent directories are created automatically."""
    if err := _guard.check_path(path):
        return err
    try:
        p = pathlib.Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"✓ Created file: {path}"
    except Exception as exc:
        return f"✗ create_file failed: {exc}"


@tool
def read_file(path: str) -> str:
    """Read and return the full text content of a file."""
    if err := _guard.check_path(path):
        return err
    try:
        return pathlib.Path(path).read_text(encoding="utf-8")
    except Exception as exc:
        return f"✗ read_file failed: {exc}"


@tool
def list_directory(path: str = ".") -> str:
    """List all files and sub-folders inside a directory."""
    if err := _guard.check_path(path):
        return err
    try:
        p = pathlib.Path(path)
        entries = sorted(p.iterdir(), key=lambda e: (e.is_file(), e.name.lower()))
        if not entries:
            return f"{path}/ (empty)"
        lines = [f"  {'[dir] ' if e.is_dir() else '[file]'} {e.name}" for e in entries]
        return f"{path}/\n" + "\n".join(lines)
    except Exception as exc:
        return f"✗ list_directory failed: {exc}"


@tool
def delete_file(path: str) -> str:
    """Delete a single file at the given path."""
    if err := _guard.check_path(path):
        return err
    try:
        pathlib.Path(path).unlink(missing_ok=True)
        return f"✓ Deleted file: {path}"
    except Exception as exc:
        return f"✗ delete_file failed: {exc}"


@tool
def delete_folder(path: str) -> str:
    """Delete a folder and all its contents recursively."""
    if err := _guard.check_path(path):
        return err
    try:
        shutil.rmtree(path)
        return f"✓ Deleted folder: {path}"
    except Exception as exc:
        return f"✗ delete_folder failed: {exc}"


@tool
def move_file(src: str, dest: str) -> str:
    """Move or rename a file or folder from src to dest."""
    if err := _guard.check_path(src, dest):
        return err
    try:
        shutil.move(src, dest)
        return f"✓ Moved '{src}' → '{dest}'"
    except Exception as exc:
        return f"✗ move_file failed: {exc}"


@tool
def create_venv(project_path: str) -> str:
    """Create a Python virtual environment (.venv) inside the given project directory."""
    if err := _guard.check_path(project_path):
        return err
    try:
        result = subprocess.run(
            ["python", "-m", "venv", ".venv"],
            cwd=project_path,
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
        pip = _pip(project_path)
        if packages:
            result = subprocess.run(
                [pip, "install", *packages],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                return f"✗ install failed: {result.stderr.strip()}"
            freeze = subprocess.run([pip, "freeze"], capture_output=True, text=True)
            (pathlib.Path(project_path) / "requirements.txt").write_text(
                freeze.stdout, encoding="utf-8"
            )
            return f"✓ Installed {', '.join(packages)} and wrote requirements.txt"
        else:
            req = pathlib.Path(project_path) / "requirements.txt"
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
        result = subprocess.run(
            shlex.split(command),
            cwd=cwd,
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


def run(llm, user_request: str) -> AgentResponse:
    """Run the filesystem agent and return a structured AgentResponse."""
    active_tools = _guard.filter_tools(_ALL_TOOLS)
    tool_map = {t.name: t for t in active_tools}
    llm_with_tools = llm.bind_tools(active_tools)

    agent_response = AgentResponse(request=user_request)

    messages: list = [
        SystemMessage(content=_SYSTEM_PROMPT),
        HumanMessage(content=user_request),
    ]

    while True:
        response: AIMessage = llm_with_tools.invoke(messages)
        messages.append(response)

        if not response.tool_calls:
            agent_response.summary = _clean(response.content)
            return agent_response

        for tc in response.tool_calls:
            fn = tool_map.get(tc["name"])
            output = fn.invoke(tc["args"]) if fn else f"✗ Unknown tool: {tc['name']}"
            agent_response.steps.append(
                ToolResult(tool=tc["name"], args=tc["args"], output=str(output))
            )
            messages.append(ToolMessage(content=str(output), tool_call_id=tc["id"]))
