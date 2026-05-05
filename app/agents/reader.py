"""Code Reader Agent — reads and searches the codebase without modifying anything.

Tools:
  - get_file_tree   : recursive directory tree with file sizes
  - read_file       : read a single file (with optional line range)
  - search_in_files : grep-style pattern search across the workspace
  - find_definition : find where a name is defined (class, def, const)
  - summarise_file  : ask the LLM to summarise what a file does

The agent is read-only — it never creates, writes, or deletes anything.
"""
from __future__ import annotations

import os
import pathlib
import re
from dataclasses import dataclass, field
from typing import Callable

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.tree import Tree


# ─── Workspace guard ─────────────────────────────────────────────────────────

_workspace: pathlib.Path | None = None
_confirm_fn: Callable | None = None   # unused for read-only, kept for API symmetry


def configure(workspace: str | None = None, confirm_fn: Callable | None = None) -> None:
    global _workspace, _confirm_fn
    _workspace = pathlib.Path(workspace).resolve() if workspace else None
    _confirm_fn = confirm_fn


def _check(path: str) -> str | None:
    """Return an error string if path escapes workspace, else None."""
    if _workspace is None:
        return None
    try:
        pathlib.Path(path).resolve().relative_to(_workspace)
        return None
    except ValueError:
        return f"✗ Permission denied: '{path}' is outside workspace '{_workspace}'"


# ─── Tools ───────────────────────────────────────────────────────────────────

# Extensions treated as text (others are skipped in search)
_TEXT_EXTS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".html", ".css", ".scss",
    ".json", ".toml", ".yaml", ".yml", ".md", ".txt", ".env",
    ".sh", ".bat", ".ps1", ".rs", ".go", ".java", ".c", ".cpp",
    ".h", ".hpp", ".rb", ".php", ".swift", ".kt", ".cs", ".sql",
    ".graphql", ".tf", ".hcl", ".ini", ".cfg", ".conf",
}

_IGNORE_DIRS = {
    ".git", ".venv", "venv", "__pycache__", "node_modules",
    ".pytest_cache", ".mypy_cache", "dist", "build", ".codemitra",
}

MAX_FILE_READ = 200   # lines — safety cap for large files
MAX_SEARCH_RESULTS = 30


@tool
def get_file_tree(path: str = ".", max_depth: int = 4) -> str:
    """
    Return a text tree of the directory structure under path, up to max_depth levels.
    Skips .git, node_modules, __pycache__, .venv, and other noise folders.
    """
    if err := _check(path):
        return err
    root = pathlib.Path(path).resolve()
    if not root.exists():
        return f"✗ Path does not exist: {path}"

    lines: list[str] = [f"{root.name}/"]

    def _walk(p: pathlib.Path, prefix: str, depth: int) -> None:
        if depth > max_depth:
            return
        try:
            entries = sorted(p.iterdir(), key=lambda e: (e.is_file(), e.name.lower()))
        except PermissionError:
            return
        entries = [e for e in entries if e.name not in _IGNORE_DIRS]
        for i, entry in enumerate(entries):
            connector = "└── " if i == len(entries) - 1 else "├── "
            if entry.is_dir():
                lines.append(f"{prefix}{connector}{entry.name}/")
                _walk(entry, prefix + ("    " if i == len(entries) - 1 else "│   "), depth + 1)
            else:
                size = entry.stat().st_size
                size_str = f" ({size:,} B)" if size < 100_000 else f" ({size / 1024:.0f} KB)"
                lines.append(f"{prefix}{connector}{entry.name}{size_str}")

    _walk(root, "", 1)
    return "\n".join(lines)


@tool
def read_file(path: str, start_line: int = 1, end_line: int = 0) -> str:
    """
    Read a file and return its text content.
    Optionally specify start_line / end_line (1-based) to return a slice.
    Returns at most 200 lines — use start_line/end_line for deeper reads.
    """
    if err := _check(path):
        return err
    p = pathlib.Path(path)
    if not p.exists():
        return f"✗ File not found: {path}"
    if p.suffix not in _TEXT_EXTS and p.suffix != "":
        return f"✗ Binary or unsupported file type: {p.suffix}"
    try:
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception as exc:
        return f"✗ read_file failed: {exc}"

    total = len(lines)
    start = max(1, start_line) - 1
    end   = min(total, end_line if end_line > 0 else start + MAX_FILE_READ)
    sliced = lines[start:end]
    header = f"# {path}  (lines {start+1}–{end} of {total})\n"
    return header + "\n".join(f"{start+1+i:>4} │ {l}" for i, l in enumerate(sliced))


@tool
def search_in_files(
    pattern: str,
    path: str = ".",
    file_glob: str = "*.py",
    case_sensitive: bool = False,
    max_results: int = 20,
) -> str:
    """
    Search for a regex pattern across all matching files under path.
    Returns file:line:content for up to max_results matches.
    file_glob filters which files are searched (e.g. '*.py', '*.ts', '*').
    """
    if err := _check(path):
        return err
    root = pathlib.Path(path).resolve()
    try:
        flags = 0 if case_sensitive else re.IGNORECASE
        rx    = re.compile(pattern, flags)
    except re.error as e:
        return f"✗ Invalid regex: {e}"

    results: list[str] = []
    import fnmatch

    for fpath in sorted(root.rglob(file_glob)):
        if any(part in _IGNORE_DIRS for part in fpath.parts):
            continue
        if fpath.suffix not in _TEXT_EXTS and fpath.suffix != "":
            continue
        if len(results) >= max_results:
            break
        try:
            text = fpath.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            if rx.search(line):
                rel = fpath.relative_to(root)
                results.append(f"{rel}:{lineno}: {line.rstrip()}")
                if len(results) >= max_results:
                    break

    if not results:
        return f"No matches for '{pattern}' in {file_glob} files under {path}"
    header = f"# Found {len(results)} match(es) for '{pattern}' (cap {max_results})\n"
    return header + "\n".join(results)


@tool
def find_definition(name: str, path: str = ".") -> str:
    """
    Find where a class, function, variable, or constant named 'name' is defined.
    Searches .py files for 'def name', 'class name', 'name =', 'NAME ='.
    """
    if err := _check(path):
        return err
    patterns = [
        rf"^\s*(def|class|async def)\s+{re.escape(name)}\b",
        rf"^\s*{re.escape(name)}\s*[=:]",
    ]
    combined = re.compile("|".join(patterns), re.IGNORECASE)
    root = pathlib.Path(path).resolve()
    results: list[str] = []

    for fpath in sorted(root.rglob("*.py")):
        if any(part in _IGNORE_DIRS for part in fpath.parts):
            continue
        try:
            for lineno, line in enumerate(
                fpath.read_text(encoding="utf-8", errors="replace").splitlines(), 1
            ):
                if combined.search(line):
                    rel = fpath.relative_to(root)
                    results.append(f"{rel}:{lineno}: {line.rstrip()}")
        except Exception:
            continue

    if not results:
        return f"No definition found for '{name}' in {path}"
    return "\n".join(results)


@tool
def grep_symbol(symbol: str, path: str = ".") -> str:
    """
    Find all usages of a symbol (class, function, variable) across the workspace.
    Searches all text files — broader than find_definition which only finds declarations.
    Returns up to 30 matches with file, line number, and context.
    """
    if err := _check(path):
        return err
    pattern = re.compile(re.escape(symbol), re.IGNORECASE)
    root = pathlib.Path(path).resolve()
    results: list[str] = []

    for fpath in sorted(root.rglob("*")):
        if any(part in _IGNORE_DIRS for part in fpath.parts):
            continue
        if fpath.suffix not in _TEXT_EXTS:
            continue
        if len(results) >= MAX_SEARCH_RESULTS:
            break
        try:
            for lineno, line in enumerate(
                fpath.read_text(encoding="utf-8", errors="replace").splitlines(), 1
            ):
                if pattern.search(line):
                    rel = fpath.relative_to(root)
                    results.append(f"{rel}:{lineno}: {line.rstrip()}")
                    if len(results) >= MAX_SEARCH_RESULTS:
                        break
        except Exception:
            continue

    if not results:
        return f"No usages of '{symbol}' found in {path}"
    return f"# Usages of '{symbol}' ({len(results)} found)\n" + "\n".join(results)


# ─── All tools ────────────────────────────────────────────────────────────────

_ALL_TOOLS = [get_file_tree, read_file, search_in_files, find_definition, grep_symbol]


# ─── System prompt ────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """You are the Code Reader Agent inside CodeMitra.
You can ONLY read and analyse — never create, write, or delete files.

## Available tools
- get_file_tree    : show the directory tree (skip noise folders)
- read_file        : read a file, optionally a line range
- search_in_files  : regex search across files matching a glob (*.py, *.ts, *)
- find_definition  : find where a name is defined (class, def, const)
- grep_symbol      : find all usages of a symbol across the workspace

## Rules
1. Always start with get_file_tree to understand the project structure.
2. Use read_file for full file content; use search_in_files to find specific code.
3. Summarise your findings in plain English.
4. Never make up code that you haven't actually read.
5. If a file is too large (>200 lines returned), use start_line/end_line to page through it.

## Output rules
- Final reply must be plain English. No JSON, no tool-call syntax.
- Quote relevant code snippets inline when helpful.
"""


# ─── Agent runner ─────────────────────────────────────────────────────────────

@dataclass
class ReaderResponse:
    request: str
    findings: list[str] = field(default_factory=list)   # key discovered facts
    summary: str = ""
    tokens_in: int = 0
    tokens_out: int = 0


def run(llm, user_request: str, console: Console | None = None) -> ReaderResponse:
    """Run the code reader agent and return a ReaderResponse."""
    llm_with_tools = llm.bind_tools(_ALL_TOOLS)
    tool_map = {t.name: t for t in _ALL_TOOLS}
    response_obj = ReaderResponse(request=user_request)

    messages: list = [
        SystemMessage(content=_SYSTEM_PROMPT),
        HumanMessage(content=user_request),
    ]

    while True:
        response: AIMessage = llm_with_tools.invoke(messages)
        meta = getattr(response, "usage_metadata", None) or {}
        response_obj.tokens_in  += meta.get("input_tokens", 0)
        response_obj.tokens_out += meta.get("output_tokens", 0)
        messages.append(response)

        if not response.tool_calls:
            response_obj.summary = (response.content or "").strip()
            return response_obj

        for tc in response.tool_calls:
            if console is not None:
                args_str = ", ".join(
                    f"{k}={repr(str(v))[:50]}" for k, v in tc["args"].items()
                )
                console.print(
                    f"  [dim magenta]⋯[/dim magenta] [magenta]{tc['name']}[/magenta][dim]({args_str})[/dim]"
                )
            fn = tool_map.get(tc["name"])
            output = fn.invoke(tc["args"]) if fn else f"✗ Unknown tool: {tc['name']}"
            response_obj.findings.append(f"{tc['name']}: {str(output)[:200]}")
            messages.append(ToolMessage(content=str(output), tool_call_id=tc["id"]))


# ─── Render ───────────────────────────────────────────────────────────────────

def render(response: ReaderResponse) -> Panel:
    """Build a Rich Panel for the reader agent's findings."""
    from rich.markdown import Markdown
    return Panel(
        Markdown(response.summary),
        title="[bold magenta]Code Reader[/bold magenta]",
        border_style="magenta",
    )


# ─── Routing tool (for main LLM) ─────────────────────────────────────────────

def make_routing_tool(llm, console: Console | None = None):
    """Return a LangChain tool the main LLM can call to invoke this agent."""
    @tool
    def read_codebase(request: str) -> str:
        """
        Read, search, or analyse files in the project without modifying anything.
        Use when the user asks to explain code, find a function, search for a pattern,
        show the project structure, or understand what a file does.
        Pass the full user request unchanged.
        """
        resp = run(llm, request, console=console)
        return resp.summary
    return read_codebase
