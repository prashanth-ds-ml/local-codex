import difflib
import gc
import os
import pathlib
import re
import subprocess
import sys
import traceback
import getpass
from datetime import datetime

import typer
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.align import Align
from rich.rule import Rule
from rich.table import Table
from prompt_toolkit import PromptSession
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.shortcuts import radiolist_dialog

from app.llm import get_cloud_llm, get_local_llm
from app.prompts import SYSTEM_PROMPT
from app.agents import filesystem
from app.agents import codeintel as codeintel_agent
from app.agents import explainer as explainer_agent
from app.agents import reviewer as reviewer_agent
from app.agents import session as session_agent
from app.agents import shell as shell_agent
from app.agents import reader as reader_agent
from app.agents import planner as planner_agent
from app.agents import web as web_agent
from app.agents.response import render
from app import config, memory, skills as skills_registry

cli = typer.Typer(invoke_without_command=True, add_completion=False)


console = Console()

try:
    # prefer direct import
    from misc.ascii import generate_codemitra_banner_art, generate_title_art
except Exception:
    # ensure project root is on sys.path when running as script
    import sys
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.append(str(root))
    from misc.ascii import generate_codemitra_banner_art, generate_title_art




def show_banner():
    try:
        title = generate_codemitra_banner_art()
    except Exception:
        from rich.text import Text
        title = Text("  CodeMitra  ", style="bold #87ceeb")

    from rich.console import Group
    from rich.text import Text as RichText
    subtitle = Align.center(RichText("Your local AI coding companion", style="bold #9aa4af"))
    p1 = Align.center(RichText.assemble(("◆", "#87ceeb"), ("  Powered by Ollama", "dim")))
    p2 = Align.center(RichText.assemble(("◆", "#87ceeb"), ("  Runs 100% offline", "dim")))
    p3 = Align.center(RichText.assemble(("◆", "#87ceeb"), ("  No data leaves your machine", "dim")))
    hint = Align.center(RichText.assemble(
        ("Type ", "dim"), ("exit", "#87ceeb"), (" or ", "dim"), ("quit", "#87ceeb"), (" to leave", "dim")
    ))

    body = Group(
        Align.center(title),
        RichText(""),
        subtitle,
        RichText(""),
        p1, p2, p3,
        RichText(""),
        hint,
    )

    console.print(
        Align.center(
            Panel(
                body,
                border_style="#87ceeb",
                padding=(1, 3),
                width=106,
            )
        )
    )


_CODEMITRA_MD_TEMPLATE = """\
# Project Rules

<!-- CodeMitra will follow these rules in every response. -->

## General
- Always write clean, readable, well-structured code
- Use meaningful names for variables, functions, and files
- Keep functions small and focused on a single responsibility
- Add comments only where the intent is not obvious from the code
- Do not delete files without explicit permission

## Project Management
- Always check if a file or folder exists before creating it
- Ask for the project path if not provided
- Create a virtual environment before installing any packages
- Update requirements.txt / package.json when adding dependencies

## AI / ML Projects
- Use clear, modular pipeline design (data → model → eval → serve)
- Log experiments with enough detail to reproduce results
- Keep model configs separate from code (use config files or env vars)
- Document dataset sources and any preprocessing steps

## Web / API Projects
- Separate concerns: routes → services → data layer
- Validate all inputs at the boundary
- Never hardcode secrets — use .env files
- Write at least one test per endpoint

## Safety
- Show a diff or summary before applying bulk changes
- Run tests before marking any task as complete
- Confirm before running destructive commands
"""

_CODEMITRA_TOML_TEMPLATE = """\
model = ""                   # legacy fallback; prefer local_model
local_model = ""             # leave empty to pick at startup
codegen_model = "kimi-k2.5:cloud"  # used only when cloud codegen is enabled
temperature = 0.2
session_mode = "approve"     # read-only | plan | approve | auto
show_reasoning = false       # show <think> output panels when available
memory_enabled = false
require_diff_approval = true
auto_compact_threshold = 120000  # auto-compact when session tokens exceed this
num_ctx = 131072                 # requested Ollama context window when supported
ollama_api_key = ""          # optional; leave empty to be prompted at startup
ollama_local_base_url = "http://localhost:11434"
ollama_cloud_base_url = "https://ollama.com"
allowed_roots = []           # extra folders CodeMitra may inspect/edit beyond the workspace
disabled_tools = []          # tool names to disable from the filesystem agent
disabled_commands = []       # shell executables to block (e.g. ["python", "git"])
instruction_files = ["AGENTS.md", ".codemitra/instructions.md", ".github/copilot-instructions.md"]
skill_dirs = ["skills", ".codemitra/skills"]
"""

_DEFAULT_CLOUD_CODEGEN_MODEL = "kimi-k2.5:cloud"


def _run_init() -> None:
    """Shared init logic — works from CLI and from inside the chat REPL."""
    cwd = pathlib.Path.cwd()
    created = []

    rules_path = cwd / "CODEMITRA.md"
    if rules_path.exists():
        console.print("[yellow]CODEMITRA.md already exists — skipped.[/yellow]")
    else:
        rules_path.write_text(_CODEMITRA_MD_TEMPLATE, encoding="utf-8")
        created.append("CODEMITRA.md")

    toml_path = cwd / "codemitra.toml"
    if toml_path.exists():
        console.print("[yellow]codemitra.toml already exists — skipped.[/yellow]")
    else:
        toml_path.write_text(_CODEMITRA_TOML_TEMPLATE, encoding="utf-8")
        created.append("codemitra.toml")

    if created:
        console.print(f"[green]✓ Created:[/green] {', '.join(created)}")
        console.print("[dim]Edit CODEMITRA.md to add your project rules.[/dim]")
    else:
        console.print("[dim]Nothing to create — already initialised.[/dim]")

    # Always scaffold the Obsidian memory vault (skips existing files)
    vault_files = memory.init_memory(str(cwd))
    if vault_files:
        console.print(f"\n[green]✓ Memory vault:[/green] .codemitra/")
        for f in vault_files:
            console.print(f"  [dim cyan]  {f}[/dim cyan]")
        console.print(
            "\n[dim]Tip: Open [bold].codemitra/[/bold] as an Obsidian vault for "
            "graph view, search, and history.[/dim]"
        )
    else:
        console.print("[dim]Memory vault already exists — skipped.[/dim]")


@cli.command("init")
def cmd_init():
    """Initialise CodeMitra in the current project directory."""
    _run_init()


@cli.callback(invoke_without_command=True)
def main(ctx: typer.Context):
    """CodeMitra — local AI coding agent powered by Ollama."""
    if ctx.invoked_subcommand is not None:
        return
    _chat()


def _extract_thinking(content: str) -> tuple[str, str]:
    """Split <think>…</think> from content. Returns (thinking_text, clean_reply)."""
    match = re.search(r"<think>(.*?)</think>", content, re.DOTALL)
    if not match:
        return "", content
    thinking = match.group(1).strip()
    reply = (content[: match.start()] + content[match.end() :]).strip()
    return thinking, reply


def _get_tokens(response) -> tuple[int, int]:
    """Return (input_tokens, output_tokens) from a LangChain response."""
    meta = getattr(response, "usage_metadata", None) or {}
    return meta.get("input_tokens", 0), meta.get("output_tokens", 0)


# ── Known friendly error patterns ────────────────────────────────────────────
_ERROR_HINTS: list[tuple[str, str]] = [
    ("connection refused",        "Ollama is not running. Start it with: ollama serve"),
    ("ollama",                    "Cannot reach Ollama. Is it running? Try: ollama serve"),
    ("validation error",          "The model returned malformed tool arguments. Try rephrasing your request."),
    ("list_type",                 "Package list was not recognised. Try: install pygame numpy"),
    ("context length",            "The conversation is too long. Use /reset to start a fresh session."),
    ("requires more system memory", "The selected model is too large for available RAM. Use `/hibernate` to save state, unload the local model, and continue with a fresh session, or restart CodeMitra with a smaller model."),
    ("rate_limit",                "Request rate-limited. Wait a moment and try again."),
]


def _friendly_error(exc: Exception) -> str:
    """Return a human-readable error message for known exception patterns."""
    msg = str(exc).lower()
    for pattern, hint in _ERROR_HINTS:
        if pattern in msg:
            return hint
    return f"Unexpected error: {exc}"


def _log_error(workspace: str, exc: Exception) -> None:
    """Append full traceback to .codemitra/errors.log."""
    try:
        log_dir = pathlib.Path(workspace) / ".codemitra"
        log_dir.mkdir(exist_ok=True)
        log_path = log_dir / "errors.log"
        from datetime import datetime
        entry = f"\n{'='*60}\n{datetime.now().isoformat()}\n{traceback.format_exc()}\n"
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(entry)
    except Exception:
        pass  # never crash the crash handler


# ── Slash command completer ───────────────────────────────────────────────────
_SLASH_COMMANDS = [
    "/init", "/run", "/plan", "/memory", "/context", "/status", "/model",
    "/history", "/resume", "/rename", "/diff", "/review", "/explain", "/symbols", "/search", "/open-url", "/undo", "/fix", "/tasks", "/skills", "/brainstorm", "/mode", "/thinking", "/permissions", "/compact", "/hibernate", "/reset", "/help",
    "exit", "quit",
]
_SESSION_MODES = ("read-only", "plan", "approve", "auto")
_FIX_MAX_ATTEMPTS = 3
_LAST_SHELL_COMMAND: str | None = None

_GREETING_INPUTS = {
    "hi", "hello", "hey", "hiya", "yo",
    "good morning", "good afternoon", "good evening",
}
_SOFT_PREFIXES = (
    "please ",
    "can you ",
    "could you ",
    "would you ",
    "i want to ",
    "i need to ",
    "i need you to ",
    "help me ",
)
_WEB_SEARCH_PREFIXES = (
    "search the web for ",
    "search online for ",
    "look up ",
    "find online ",
    "browse the web for ",
)
_PLAN_START_KEYWORDS = (
    "build", "create", "make", "scaffold", "set up", "setup",
    "implement", "develop", "refactor", "fix", "debug", "add", "update", "rename",
    "generate", "start a", "start an", "remove", "delete", "clean up", "cleanup",
)
_PLAN_COMPLEXITY_HINTS = (
    "using", "with", "should", "need to", "project", "app", "application",
    "api", "game", "feature", "workflow", "codebase", "multiple",
    "tests", "bug", "module", "unwanted", "folder", "directories", "references", "throughout", "wherever", "root folder",
)
_DIRECT_COMMAND_HELP_HINTS = (
    "give me commands",
    "give me the commands",
    "command to run",
    "commands to run",
    "how do i run",
    "how to run",
    "how can i run",
    "how do i launch",
    "how to launch",
)
_PROJECT_SUMMARY_HINTS = (
    "what do you understand",
    "tell me what you understand",
    "go through the folder",
    "go through the project",
    "understand this project",
    "understand it",
    "understand the folder",
    "explain it",
    "tell me about this project",
    "tell me about it",
    "what have you understood",
)
_CURRENT_FOLDER_HINTS = (
    "where are we",
    "which dir",
    "which directory",
    "current dir",
    "current directory",
    "this folder",
    "this directory",
    "tell me about this folder",
    "what folder does it contain",
    "what folders does it contain",
    "what files does it contain",
    "what does it contain",
    "what is in this folder",
    "what's in this folder",
    "what is in this directory",
    "what's in this directory",
)
_UNDERSTAND_ALIAS_HINTS = (
    "understand",
    "understand this",
    "explain this",
    "tell me about this",
    "tell me about it",
)
_NAVIGATION_PATTERNS = (
    r"^(?:go|got)\s+to\s+(.+)$",
    r"^navigate\s+to\s+(.+)$",
    r"^move\s+to\s+(.+)$",
    r"^move\s+into\s+(.+)$",
    r"^switch\s+to\s+(.+)$",
    r"^change\s+to\s+(.+)$",
    r"^open\s+(.+)$",
    r"^enter\s+(.+)$",
    r"^cd\s+(.+)$",
)
_WORKSPACE_SELECTION_PATTERNS = (
    r"^work\s+with\s+(.+)$",
    r"^work\s+on\s+(.+)$",
    r"^use\s+(.+)$",
)
_SMALL_TALK_HINTS = (
    "how are you",
    "how are you doing",
    "what's up",
    "whats up",
    "thank you",
    "thanks",
    "okay",
    "ok",
    "sounds good",
)
_SMALL_TALK_EXACT_HINTS = {"okay", "ok", "sounds good"}
_BRAINSTORM_HINTS = (
    "brainstorm",
    "ideas",
    "idea",
    "interesting",
    "what should we build",
    "give me ideas",
    "do you have any ideas",
    "explore options",
    "let's explore",
    "lets explore",
    "always wanted to build",
    "wanted to build",
    "i have an idea",
    "i had an idea",
)
_CLEANUP_REQUEST_HINTS = (
    "remove unwanted",
    "remove unwnated",
    "remove others",
    "remove the others",
    "clean up",
    "cleanup",
    "keep only",
    "delete unwanted",
    "delete others",
)
_DELETE_PROJECT_HINTS = (
    "delete this project",
    "delete the project",
    "delete this folder",
    "delete this repo",
    "start fresh again",
)
_CLEANUP_NAME_HINTS = {
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    "build",
    "dist",
    "demo",
    "demos",
    "demo-live",
    "demo-workspace",
    "example",
    "examples",
    "sample",
    "samples",
    "tmp",
    "temp",
    "backup",
    "old",
}
_EXPLAIN_HINTS = (
    "explain",
    "what is",
    "what does",
    "understand",
    "go through",
    "analyze",
    "analyse",
    "review",
)
_CHANGE_HINTS = (
    "create",
    "make",
    "add",
    "change",
    "rename",
    "move",
    "update",
    "delete",
    "remove",
    "refactor",
    "edit",
)
_ACTIONABLE_SETUP_HINTS = (
    "create",
    "make",
    "add",
    "set up",
    "setup",
    "initialize",
    "init",
)
_ACTIONABLE_SETUP_OBJECT_HINTS = (
    "folder",
    "directory",
    "file",
    ".venv",
    "venv",
    "readme",
    "notes",
    "doc",
    "docs",
    "vault",
    "obsidian",
)
_SIMPLE_CHANGE_PATTERNS = (
    r"^(create|make|add)\s+(a\s+|an\s+)?folder\b",
    r"^(create|make|add)\s+(a\s+|an\s+)?directory\b",
    r"^(create|make|add)\s+(a\s+|an\s+)?file\b",
    r"^(rename|move)\s+(the\s+)?(file|folder|directory)\b",
)
_RUN_HINTS = (
    "run ",
    "execute ",
    "start ",
    "launch ",
    "test ",
    "pytest",
    "python ",
    "npm ",
    "node ",
)


def _make_completer(workspace: str) -> WordCompleter:
    """Build a completer from slash commands + filenames in workspace."""
    try:
        files = [
            str(p.relative_to(workspace))
            for p in pathlib.Path(workspace).rglob("*")
            if p.is_file() and not any(part.startswith(".") or part == "__pycache__"
                                       for part in p.parts)
        ][:80]  # cap at 80 to keep startup fast
    except Exception:
        files = []
    return WordCompleter(
        _SLASH_COMMANDS + files,
        sentence=True,
        match_middle=False,
    )


def _build_prompt_label(model: str, session_mode: str = "approve") -> str:
    """Return the interactive prompt label shown before each user input."""
    model_short = model.split(":")[0]
    return f"\n[CodeMitra · {session_mode}] ({model_short})> "


def _shorten_display(text: str, max_len: int = 28) -> str:
    value = re.sub(r"\s+", " ", (text or "").strip())
    if len(value) <= max_len:
        return value
    return value[: max_len - 1].rstrip() + "…"


def _build_context_reply(total_tokens: int, auto_compact_threshold: int, num_ctx: int) -> str:
    pct = min(100, int(total_tokens / max(auto_compact_threshold, 1) * 100))
    bar_filled = pct // 5
    bar = "█" * bar_filled + "░" * (20 - bar_filled)
    state = "Healthy" if pct < 80 else ("Getting heavy" if pct < 100 else "Ready to compact")
    return (
        "## Context window\n\n"
        f"- **Requested max context:** `{num_ctx:,}`\n"
        f"- **Auto-compact threshold:** `{auto_compact_threshold:,}`\n"
        f"- **Current session usage:** `{total_tokens:,}` tokens\n"
        f"- **Load:** `{pct}%`\n"
        f"- **State:** {state}\n"
        f"- **Usage bar:** `{bar}`\n\n"
        "Use `/compact` to compress the conversation while keeping the active session alive."
    )


def _build_hibernation_reply(
    *,
    workspace: str,
    model: str,
    session_name: str,
    shell_cwd: str,
    total_tokens: int,
    auto_compact_threshold: int,
    free_ram_before: float | None,
    free_ram_after: float | None,
    unload_detail: str,
) -> str:
    ram_before = f"`{free_ram_before:.1f} GB`" if free_ram_before is not None else "Unknown"
    ram_after = f"`{free_ram_after:.1f} GB`" if free_ram_after is not None else "Unknown"
    return (
        "## Session hibernated\n\n"
        f"- **Session:** `{session_name}`\n"
        f"- **Workspace:** `{workspace}`\n"
        f"- **Shell cwd:** `{shell_cwd}`\n"
        f"- **Model unloaded:** `{model}`\n"
        f"- **Session usage before reset:** {_format_session_usage(total_tokens, auto_compact_threshold)}\n"
        f"- **Available RAM:** {ram_before} → {ram_after}\n"
        f"- **Persistence:** activity, context, plan timestamp, and session metadata updated\n"
        f"- **Unload result:** {unload_detail}\n\n"
        "CodeMitra cleared the in-memory conversation and will continue from the saved workspace state on the next turn. Use `/resume` if you want a compact recap first."
    )


def _hibernate_session(
    *,
    workspace: str,
    model: str,
    system_prompt: str,
    total_tokens: int,
    auto_compact_threshold: int,
) -> tuple[list, int, int, str]:
    session_meta = session_agent.ensure_session(workspace)
    session_name = session_meta.get("name", pathlib.Path(workspace).resolve().name)
    shell_cwd = shell_agent.get_cwd()
    free_ram_before = config.get_available_system_memory_gib()

    memory.save_session_metadata(
        workspace,
        {
            **session_meta,
            "last_hibernated_at": datetime.now().isoformat(timespec="seconds"),
            "last_hibernated_cwd": shell_cwd,
            "last_hibernated_model": model,
            "last_hibernated_usage_tokens": total_tokens,
        },
    )

    unload_ok, unload_detail = config.stop_local_model(model)
    if not unload_ok:
        unload_detail = f"{unload_detail} The session was still reset and saved."

    gc.collect()
    recovered_messages = [SystemMessage(content=system_prompt)]
    free_ram_after = config.get_available_system_memory_gib()
    reply = _build_hibernation_reply(
        workspace=workspace,
        model=model,
        session_name=session_name,
        shell_cwd=shell_cwd,
        total_tokens=total_tokens,
        auto_compact_threshold=auto_compact_threshold,
        free_ram_before=free_ram_before,
        free_ram_after=free_ram_after,
        unload_detail=unload_detail,
    )
    memory.record_hibernation(workspace, reply)
    return recovered_messages, 0, 0, reply


def _build_permissions_reply(cfg: dict, session_mode: str) -> str:
    allowed_roots = cfg.get("allowed_roots") or []
    disabled_tools = cfg.get("disabled_tools") or []
    disabled_commands = cfg.get("disabled_commands") or []
    roots_text = ", ".join(f"`{path}`" for path in allowed_roots) if allowed_roots else "None"
    tools_text = ", ".join(f"`{name}`" for name in disabled_tools) if disabled_tools else "None"
    commands_text = ", ".join(f"`{name}`" for name in disabled_commands) if disabled_commands else "None"
    return (
        "## Permissions\n\n"
        f"- **Mode:** `{session_mode}`\n"
        f"- **Behavior:** {_mode_summary(session_mode)}\n"
        f"- **Workspace:** `{cfg['workspace']}`\n"
        f"- **Current shell cwd:** `{shell_agent.get_cwd()}`\n"
        f"- **Additional allowed roots:** {roots_text}\n"
        f"- **Disabled file tools:** {tools_text}\n"
        f"- **Disabled shell commands:** {commands_text}\n"
        "- **Shell trust:** approved commands can be trusted per directory and then auto-approved on repeat.\n\n"
        "Use `/mode` to change the session behavior. Edit `codemitra.toml` to change allowed roots or disabled tools and commands."
    )


def _build_plan_execution_blocked_reply(session_mode: str, *, active_plan: bool = False) -> str:
    target = "the active plan" if active_plan else "plan steps"
    ending = "continue." if active_plan else "act."
    return (
        f"CodeMitra is in `{session_mode}` mode, so it will not execute {target} yet. "
        f"Use `/mode approve` or `/mode auto` to {ending}"
    )


def _build_plan_unapproved_reply() -> str:
    return (
        "The active plan has not been approved yet. "
        "Use `/plan approve` first, then `/plan next` for one step or `/plan run` for the remaining steps."
    )


def _build_project_instructions_prompt(instructions: list[dict[str, str]]) -> str:
    """Format loaded project instruction files for the system prompt."""
    sections: list[str] = []
    for item in instructions:
        path = item.get("path", "project instructions")
        content = (item.get("content") or "").strip()
        if not content:
            continue
        sections.append(f"### {path}\n{content}")
    if not sections:
        return ""
    return "## Project Instructions\n" + "\n\n".join(sections)


def _build_skills_prompt(skills: list[skills_registry.Skill]) -> str:
    return skills_registry.format_prompt(skills)


def _build_skills_reply(
    skills: list[skills_registry.Skill],
    raw: str = "/skills",
    *,
    workspace: str | None = None,
) -> str:
    target = raw.strip()[7:].strip() if raw.strip().lower().startswith("/skills") else raw.strip()
    if target.startswith("show "):
        query = target[5:].strip()
        if not query:
            return "Usage: `/skills show <name>`"
        skill = skills_registry.find(skills, query)
        if skill is None:
            return f"No matching skill found for `{query}`. Use `/skills` to list available skills."
        if workspace is None:
            return f"## {skill.name}\n\n- **Path:** `{skill.path}`\n- **Description:** {skill.description}"
        body = skills_registry.read_body(workspace, skill)
        if body is None:
            return f"Could not read `{skill.path}`."
        return f"## {skill.name}\n\n- **Path:** `{skill.path}`\n- **Description:** {skill.description}\n\n```md\n{body}\n```"

    if target:
        return "Usage: `/skills` or `/skills show <name>`."

    if not skills:
        return (
            "No CodeMitra skills found yet.\n\n"
            "Add skills under `skills/<name>/SKILL.md` or `.codemitra/skills/<name>/SKILL.md`."
        )
    lines = ["## CodeMitra skills", ""]
    for skill in skills:
        lines.append(f"- **{skill.name}** — `{skill.path}`")
        lines.append(f"  {skill.description}")
    lines.extend(["", "Use `/skills show <name>` to inspect a skill."])
    return "\n".join(lines)


def _build_bottom_toolbar(
    *,
    session_mode: str,
    model: str,
    cwd: str,
    total_tokens: int,
    auto_compact_threshold: int,
    current_task: str,
    background_tasks: int,
) -> str:
    pct = min(100, int(total_tokens / max(auto_compact_threshold, 1) * 100))
    return (
        f" {session_mode}  ·  {model.split(':')[0]}  ·  {pathlib.Path(cwd).name or cwd}  ·  "
        f"ctx {pct}%  ·  bg {background_tasks}  ·  task {_shorten_display(current_task, 32)}  ·  Ctrl+G editor "
    )


def _make_key_bindings() -> KeyBindings:
    bindings = KeyBindings()

    @bindings.add("c-g")
    def _(event) -> None:
        event.app.current_buffer.open_in_editor()

    return bindings


def _clear_terminal() -> None:
    """Clear the terminal before rendering startup UI."""
    try:
        console.clear()
    except Exception:
        try:
            os.system("cls" if os.name == "nt" else "clear")
        except Exception:
            pass


def _build_progress_message(message: str, detail: str | None = None) -> str:
    text = f"● {message}"
    if detail:
        text += f"\n  {detail}"
    return text


def _print_progress_message(message: str, detail: str | None = None, *, color: str = "cyan") -> None:
    from rich.text import Text

    console.print()
    console.print(Text.assemble(("● ", f"bold {color}"), (message, "white")))
    if detail:
        console.print(Text(detail, style="dim"))


def _build_intent_progress_message(intent: str, user_input: str) -> tuple[str, str | None] | None:
    if intent == "brainstorm":
        return ("Exploring the idea space", "I’ll keep it practical and structured.")
    if intent == "plan":
        return ("This looks like a multi-step request", "Starting with brainstorming and a plan before making changes.")
    if intent == "run-help":
        return ("Turning this into concrete terminal steps", None)
    if _extract_navigation_target(user_input):
        return ("Navigating to the folder", "I’ll switch the active shell directory.")
    if intent == "explain" and _is_current_folder_request(user_input):
        return ("Inspecting the current folder", "I’ll answer with the active directory and its immediate contents.")
    if intent == "explain" and _is_understand_alias_request(user_input):
        return ("Understanding the current project", "I’ll summarize the active folder instead of sending this to the raw chat model.")
    if intent == "explain" and _is_project_summary_request(user_input):
        return ("Inspecting the workspace first", "I’ll summarize purpose, structure, blockers, and likely next steps.")
    if intent == "change" and _is_cleanup_request(user_input):
        return ("Preparing a cleanup preview", "I’ll show likely disposable files before removing anything.")
    return None


def _normalize_session_mode(raw: str | None) -> str:
    mode = (raw or "approve").strip().lower()
    return mode if mode in _SESSION_MODES else "approve"


def _mode_summary(mode: str) -> str:
    summaries = {
        "read-only": "Read and inspect only. No shell execution except built-in navigation/listing helpers.",
        "plan": "Inspect and plan work. Code edits and shell execution stay blocked.",
        "approve": "Ask before shell commands and file changes. Best default for active coding.",
        "auto": "Allow in-workspace edits and shell commands without interactive approval.",
    }
    return summaries.get(mode, summaries["approve"])


def _is_simple_greeting(user_input: str) -> bool:
    """Return True when the input is a short greeting that should bypass the LLM."""
    normalized = re.sub(r"\s+", " ", user_input.strip().lower())
    normalized = re.sub(r"[!?.,]+$", "", normalized)
    if normalized in _GREETING_INPUTS:
        return True

    tokens = normalized.split()
    if not tokens or len(tokens) > 4:
        return False

    if len(tokens) >= 2 and " ".join(tokens[:2]) in _GREETING_INPUTS:
        return True

    return tokens[0] in {"hi", "hello", "hey", "hiya", "yo"}


def _build_greeting_reply() -> str:
    """Return a stable greeting so first-run UX does not depend on model quality."""
    return (
        "Hello - I'm CodeMitra, your local coding assistant.\n\n"
        "I can inspect code, run commands, help plan work, and make file changes inside your workspace. "
        "Tell me what you want to build, debug, or understand."
    )


def _is_small_talk(user_input: str) -> bool:
    normalized = re.sub(r"\s+", " ", user_input.strip().lower())
    normalized = re.sub(r"[!?.,]+$", "", normalized)
    for hint in _SMALL_TALK_HINTS:
        if hint in _SMALL_TALK_EXACT_HINTS:
            if hint == normalized:
                return True
            continue
        if hint in normalized:
            return True
    return False


def _is_understand_alias_request(user_input: str) -> bool:
    normalized = re.sub(r"\s+", " ", user_input.strip().lower())
    normalized = re.sub(r"[!?.,]+$", "", normalized)
    return normalized in _UNDERSTAND_ALIAS_HINTS


def _normalize_routing_phrase(user_input: str) -> str:
    normalized = _strip_soft_prefixes(user_input)
    normalized = re.sub(r"\s+", " ", normalized.strip().lower())
    normalized = re.sub(r"[!?.,]+$", "", normalized)
    normalized = re.sub(r"^great\s+", "", normalized)
    normalized = re.sub(r"^(?:ok|okay)\s+", "", normalized)
    normalized = re.sub(r"^lets\s+", "", normalized)
    normalized = re.sub(r"^let's\s+", "", normalized)
    return normalized


def _normalize_entry_name(value: str) -> str:
    normalized = re.sub(r"[-_.]+", " ", value.strip().lower())
    return re.sub(r"\s+", " ", normalized).strip()


def _extract_navigation_target(user_input: str) -> str | None:
    normalized = _normalize_routing_phrase(user_input)
    for pattern in _NAVIGATION_PATTERNS:
        match = re.match(pattern, normalized)
        if not match:
            continue
        target = match.group(1).strip()
        target = re.split(r"\s+(?:so that|so we can|so i can|and)\s+", target, maxsplit=1)[0].strip()
        target = re.sub(r"\b(?:folder|directory)\b", "", target).strip()
        target = re.sub(r"\s+", " ", target).strip()
        if target in {"", "the", "this", "that"}:
            return None
        return target
    return None


def _extract_workspace_selection_target(user_input: str, cwd: str) -> str | None:
    normalized = _normalize_routing_phrase(user_input)
    target_text = None
    for pattern in _WORKSPACE_SELECTION_PATTERNS:
        match = re.match(pattern, normalized)
        if match:
            target_text = match.group(1).strip()
            break
    if not target_text:
        return None

    target_text = re.split(r"\s+(?:so that|so we can|so i can|and)\s+", target_text, maxsplit=1)[0].strip()
    target_text = re.sub(r"\b(?:project|folder|directory)\b", "", target_text).strip()
    if target_text in {"", "the", "this", "that"}:
        return None

    try:
        root = pathlib.Path(cwd)
        candidates = [entry for entry in root.iterdir() if entry.is_dir()]
    except Exception:
        return None

    desired = _normalize_entry_name(target_text)
    exact_matches = [entry.name for entry in candidates if _normalize_entry_name(entry.name) == desired]
    if len(exact_matches) == 1:
        return exact_matches[0]
    return None


def _extract_web_search_query(user_input: str) -> str | None:
    normalized = _normalize_routing_phrase(user_input)
    for prefix in _WEB_SEARCH_PREFIXES:
        if normalized.startswith(prefix):
            query = normalized[len(prefix):].strip()
            return query or None
    return None


def _extract_url_from_input(user_input: str) -> str | None:
    match = re.search(r"https?://\S+", user_input, re.IGNORECASE)
    if not match:
        return None
    return match.group(0).rstrip(").,!?]}>")


def _build_small_talk_reply(user_input: str) -> str:
    normalized = re.sub(r"\s+", " ", user_input.strip().lower())
    if "how are you" in normalized:
        return "Doing well - ready to help you think through ideas, plan something interesting, or jump into code."
    if "thank" in normalized:
        return "You're welcome."
    if normalized in {"okay", "ok", "sounds good"}:
        return "Great - we can keep going whenever you're ready."
    return "I'm here and ready to help."


def _is_brainstorm_request(user_input: str) -> bool:
    normalized = re.sub(r"\s+", " ", user_input.strip().lower())
    if not normalized or normalized.startswith("/"):
        return False
    if _is_simple_change_request(normalized):
        return False
    if (
        any(token in normalized for token in _ACTIONABLE_SETUP_HINTS)
        and any(token in normalized for token in _ACTIONABLE_SETUP_OBJECT_HINTS)
    ):
        return False
    if any(hint in normalized for hint in _BRAINSTORM_HINTS):
        return True

    has_aspirational_prefix = any(
        phrase in normalized
        for phrase in (
            "i always wanted to",
            "i've always wanted to",
            "i have always wanted to",
            "i once read",
            "i keep thinking about",
        )
    )
    has_building_language = any(
        token in normalized
        for token in ("build", "create", "tool", "app", "product", "system")
    )
    has_reflective_goal_language = any(
        phrase in normalized
        for phrase in (
            "help me",
            "improve",
            "time management",
            "goal",
            "workflow",
            "personal",
            "work",
        )
    )
    return has_aspirational_prefix and has_building_language and has_reflective_goal_language


def _strip_soft_prefixes(user_input: str) -> str:
    normalized = re.sub(r"\s+", " ", user_input.strip().lower())
    for prefix in _SOFT_PREFIXES:
        if normalized.startswith(prefix):
            return normalized[len(prefix):].strip()
    return normalized


def _should_plan_first(user_input: str) -> bool:
    """Return True when a request is substantial enough to benefit from brainstorm + plan."""
    normalized = re.sub(r"\s+", " ", user_input.strip().lower())
    normalized_core = _strip_soft_prefixes(user_input)
    if not normalized or normalized.startswith("/"):
        return False
    if _is_simple_greeting(normalized):
        return False
    if normalized in {"continue", "next step", "proceed", "keep going", "execute the plan"}:
        return False
    if _is_simple_change_request(normalized):
        return False

    has_start_keyword = any(normalized_core.startswith(keyword) for keyword in _PLAN_START_KEYWORDS)
    has_complexity_hint = any(hint in normalized for hint in _PLAN_COMPLEXITY_HINTS)
    has_destructive_cleanup = any(keyword in normalized for keyword in ("remove", "delete", "clean up", "cleanup", "unwanted"))
    word_count = len(normalized.split())

    if has_destructive_cleanup and word_count >= 5:
        return True

    return has_start_keyword and (word_count >= 6 or has_complexity_hint)


def _is_simple_change_request(user_input: str) -> bool:
    normalized = re.sub(r"\s+", " ", user_input.strip().lower())
    if not normalized or normalized.startswith("/"):
        return False
    return any(re.match(pattern, normalized) for pattern in _SIMPLE_CHANGE_PATTERNS)


def _is_command_help_request(user_input: str) -> bool:
    normalized = re.sub(r"\s+", " ", user_input.strip().lower())
    if not normalized or normalized.startswith("/"):
        return False
    return any(hint in normalized for hint in _DIRECT_COMMAND_HELP_HINTS)


def _is_project_summary_request(user_input: str) -> bool:
    normalized = re.sub(r"\s+", " ", user_input.strip().lower())
    if not normalized or normalized.startswith("/"):
        return False
    return any(hint in normalized for hint in _PROJECT_SUMMARY_HINTS)


def _is_current_folder_request(user_input: str) -> bool:
    normalized = re.sub(r"\s+", " ", user_input.strip().lower())
    if not normalized or normalized.startswith("/"):
        return False
    return any(hint in normalized for hint in _CURRENT_FOLDER_HINTS)


def _is_cleanup_request(user_input: str) -> bool:
    normalized = re.sub(r"\s+", " ", user_input.strip().lower())
    if not normalized or normalized.startswith("/"):
        return False
    return any(hint in normalized for hint in _CLEANUP_REQUEST_HINTS) or (
        any(token in normalized for token in ("remove", "delete"))
        and any(token in normalized for token in ("unwanted", "unused", "extra", "not needed", "others", "rest"))
    )


def _is_delete_project_request(user_input: str) -> bool:
    normalized = re.sub(r"\s+", " ", user_input.strip().lower())
    if not normalized or normalized.startswith("/"):
        return False
    return any(hint in normalized for hint in _DELETE_PROJECT_HINTS)


def _classify_intent(user_input: str) -> str:
    normalized = re.sub(r"\s+", " ", user_input.strip().lower())
    if not normalized:
        return "chat"
    if normalized.startswith("/"):
        return "slash"
    if _is_simple_greeting(normalized):
        return "chat"
    if _is_small_talk(normalized):
        return "chat"
    if _is_brainstorm_request(normalized):
        return "brainstorm"
    if _is_command_help_request(normalized):
        return "run-help"
    if _is_cleanup_request(normalized):
        return "change"
    if _is_simple_change_request(normalized):
        return "change"
    if _should_plan_first(normalized):
        return "plan"
    if _is_understand_alias_request(normalized):
        return "explain"
    if _is_current_folder_request(normalized):
        return "explain"
    if _is_project_summary_request(normalized) or any(hint in normalized for hint in _EXPLAIN_HINTS):
        return "explain"
    if any(normalized.startswith(hint) or hint in normalized for hint in _RUN_HINTS):
        return "run"
    if any(normalized.startswith(hint) or hint in normalized for hint in _CHANGE_HINTS):
        return "change"
    return "chat"


def _looks_like_explicit_command(user_input: str) -> bool:
    stripped = user_input.strip()
    if not stripped:
        return False
    if re.search(r"`[^`]+`", stripped):
        return True
    lowered = stripped.lower()
    return bool(re.match(r"^(python|pytest|pip|npm|node|npx|ruff|mypy|black|isort)\b", lowered))


def _is_bang_command(user_input: str) -> bool:
    return user_input.strip().startswith("!")


def _extract_bang_command(user_input: str) -> str:
    return user_input.strip()[1:].strip()


def _read_readme_summary(workspace: str) -> str | None:
    for name in ("README.md", "readme.md"):
        path = pathlib.Path(workspace) / name
        if not path.exists():
            continue
        lines = [line.strip() for line in path.read_text(encoding="utf-8", errors="replace").splitlines() if line.strip()]
        heading_fallback: str | None = None
        for line in lines:
            if line.startswith("#"):
                if heading_fallback is None:
                    heading_fallback = line.lstrip("#").strip().rstrip(".")
                continue
            cleaned = line.lstrip("#> -*`").strip()
            if cleaned and not cleaned.lower().startswith(("usage", "install", "setup")):
                return cleaned.rstrip(".")
        if heading_fallback:
            return heading_fallback
    return None


def _detect_project_state(workspace: str, *, has_memory: bool = False, has_plan: bool = False) -> dict:
    root = pathlib.Path(workspace)
    targets = _find_run_targets(workspace)
    entrypoint = targets[0] if targets else None
    req = root / "requirements.txt"
    pyproject = root / "pyproject.toml"
    package_json = root / "package.json"
    state = {
        "workspace_name": root.name,
        "workspace_path": str(root),
        "entrypoint": entrypoint,
        "venv_exists": (root / ".venv").exists(),
        "requirements_exists": req.exists(),
        "pyproject_exists": pyproject.exists(),
        "package_json_exists": package_json.exists(),
        "is_git_repo": (root / ".git").exists(),
        "has_memory": has_memory,
        "has_plan": has_plan,
        "has_tests": any(
            (root / name).exists() for name in ("tests", "test", "pytest.ini")
        ) or bool(list(root.glob("test_*.py"))),
    }
    if state["requirements_exists"]:
        state["dependency_source"] = "requirements.txt"
    elif state["pyproject_exists"]:
        state["dependency_source"] = "pyproject.toml"
    elif state["package_json_exists"]:
        state["dependency_source"] = "package.json"
    else:
        state["dependency_source"] = None
    return state


def _find_run_targets(workspace: str) -> list[str]:
    root = pathlib.Path(workspace)
    candidates = [
        root / "main.py",
        root / "app.py",
        root / "snake.py",
    ]
    candidates.extend(
        path for path in sorted(root.glob("*/cli.py"))
        if path.parts[-2] not in {".venv", ".codemitra", "__pycache__"}
    )
    candidates.extend(
        path for path in sorted(root.glob("*/__main__.py"))
        if path.parts[-2] not in {".venv", ".codemitra", "__pycache__"}
    )
    candidates.extend(sorted(root.glob("src/*/cli.py")))
    candidates.extend(sorted(root.glob("src/*/__main__.py")))

    targets: list[str] = []
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            targets.append(f".\\{candidate.relative_to(root)}")
    return targets


def _find_run_target(workspace: str) -> str | None:
    targets = _find_run_targets(workspace)
    return targets[0] if targets else None


def _workspace_snapshot(workspace: str) -> tuple[list[str], list[str]]:
    root = pathlib.Path(workspace)
    dirs: list[str] = []
    files: list[str] = []
    for entry in sorted(root.iterdir(), key=lambda e: (e.is_file(), e.name.lower())):
        if entry.name.startswith(".") and entry.name not in {".venv", ".codemitra"}:
            continue
        if entry.is_dir():
            dirs.append(entry.name)
        else:
            files.append(entry.name)
    return dirs[:6], files[:6]


def _build_current_folder_reply(path: str, *, workspace: str | None = None) -> str:
    root = pathlib.Path(path).resolve()
    dirs, files = _workspace_snapshot(str(root))
    sections = [
        "## Current folder",
        f"- **Path:** `{root}`",
    ]
    if workspace:
        try:
            relative = root.relative_to(pathlib.Path(workspace).resolve())
            sections.append(
                f"- **Inside workspace:** `{relative}`" if str(relative) != "." else "- **Inside workspace:** workspace root"
            )
        except ValueError:
            pass
    sections.append(
        "- **Folders:** " + (", ".join(f"`{name}/`" for name in dirs) if dirs else "No top-level folders")
    )
    sections.append(
        "- **Files:** " + (", ".join(f"`{name}`" for name in files) if files else "No top-level files")
    )
    return "\n".join(sections)


def _build_project_summary(workspace: str) -> str:
    root = pathlib.Path(workspace)
    state = _detect_project_state(workspace)
    dirs, files = _workspace_snapshot(workspace)
    purpose = _read_readme_summary(workspace) or f"Project workspace: {root.name}"
    targets = _find_run_targets(workspace)
    entrypoint = state["entrypoint"] or "No obvious Python entrypoint found yet"

    blockers: list[str] = []
    if not state["venv_exists"]:
        blockers.append("No `.venv` is present yet.")
    if state["dependency_source"] and not state["venv_exists"]:
        blockers.append("Dependencies likely still need to be installed.")
    if not targets:
        blockers.append("I could not detect a clear runnable entrypoint.")

    next_steps: list[str] = []
    if not state["venv_exists"]:
        next_steps.append("Create a `.venv` in this workspace.")
    if state["dependency_source"] == "requirements.txt":
        next_steps.append("Install dependencies from `requirements.txt`.")
    elif state["dependency_source"] == "pyproject.toml":
        next_steps.append("Install the project with `pip install -e .`.")
    if targets:
        next_steps.append(f"Run `{targets[0]}` from PowerShell to verify the project starts.")

    sections = [
        f"**Purpose:** {purpose}.",
        f"**Workspace:** `{root.name}`",
        f"**Key folders:** {', '.join(f'`{d}/`' for d in dirs) if dirs else 'No top-level folders'}",
        f"**Key files:** {', '.join(f'`{f}`' for f in files) if files else 'No top-level files'}",
        f"**Entrypoint:** `{entrypoint}`" if targets else f"**Entrypoint:** {entrypoint}",
    ]
    if blockers:
        sections.append("**Current blockers:** " + " ".join(blockers))
    if next_steps:
        sections.append("**Likely next steps:** " + " ".join(next_steps))
    return "\n\n".join(sections)


def _build_startup_project_brief(workspace: str) -> str | None:
    state = _detect_project_state(workspace)
    dirs, files = _workspace_snapshot(workspace)
    purpose = _read_readme_summary(workspace)

    details: list[str] = []
    if purpose:
        details.append(f"- **Purpose:** {purpose}.")
    details.append(f"- **Workspace:** `{state['workspace_name']}`")
    if state["dependency_source"]:
        details.append(f"- **Dependencies:** `{state['dependency_source']}`")
    if state["entrypoint"]:
        details.append(f"- **Entrypoint:** `{state['entrypoint']}`")
    if state["has_tests"]:
        details.append("- **Tests:** present")
    if state["venv_exists"]:
        details.append("- **Environment:** `.venv` detected")
    elif state["dependency_source"]:
        details.append("- **Environment:** dependencies exist but `.venv` is not ready yet")
    if dirs:
        details.append("- **Top folders:** " + ", ".join(f"`{name}/`" for name in dirs[:4]))
    if files:
        details.append("- **Top files:** " + ", ".join(f"`{name}`" for name in files[:4]))
    if len(details) <= 2:
        return None
    return "## Auto-detected project brief\n\n" + "\n".join(details)


def _build_startup_status(
    workspace: str,
    *,
    has_memory: bool = False,
    has_plan: bool = False,
    session_mode: str = "approve",
    show_reasoning: bool = False,
    num_ctx: int = 131072,
    auto_compact_threshold: int = 120000,
) -> Panel:
    from rich.console import Group
    from rich.text import Text

    state = _detect_project_state(workspace, has_memory=has_memory, has_plan=has_plan)
    rows = Table.grid(padding=(0, 2))
    rows.add_column(style="cyan", no_wrap=True)
    rows.add_column(style="dim")
    rows.add_row("Workspace", state["workspace_name"])
    rows.add_row("Entrypoint", state["entrypoint"] or "Not detected yet")
    rows.add_row("Environment", ".venv ready" if state["venv_exists"] else "No .venv yet")
    rows.add_row("Mode", session_mode)
    rows.add_row("Context", f"{num_ctx:,} max · compact at {auto_compact_threshold:,}")

    suggested: list[str] = []
    if not state["venv_exists"]:
        suggested.append("Create `.venv`")
    if state["dependency_source"] == "requirements.txt":
        suggested.append("Install requirements")
    elif state["dependency_source"] == "pyproject.toml":
        suggested.append("Install editable package")
    if state["entrypoint"]:
        suggested.append("Ask “how do I run this?”")
    else:
        suggested.append("Ask “what do you understand about this project?”")

    content = Group(
        rows,
        Text(""),
        Text.from_markup(
            f"[bold]Session:[/bold] {session_agent.ensure_session(workspace).get('name', state['workspace_name'])}  ·  "
            f"[bold]Plan:[/bold] {'Loaded' if state['has_plan'] else 'None'}  ·  "
            f"[bold]Memory:[/bold] {'Loaded' if state['has_memory'] else 'None'}"
        ),
        Text.from_markup("[bold]Next:[/bold] " + "  ·  ".join(suggested)),
    )
    return Panel(content, title="[bold cyan]Session Snapshot[/bold cyan]", border_style="cyan")


def _build_startup_walkthrough() -> Panel:
    from rich.console import Group
    from rich.text import Text

    notes = Text.from_markup(
        "[bold]Start here:[/bold] ask naturally, or reach for a command when you want something specific."
    )
    examples = Text.from_markup(
        "[cyan]Understand[/cyan]  what do you understand about this project?\n"
        "[cyan]Plan[/cyan]  /plan build a goal tracker app\n"
        "[cyan]Inspect[/cyan]  /review  ·  /explain app\\main.py  ·  /symbols helper\n"
        "[cyan]Search[/cyan]  /search python packaging best practices"
    )
    return Panel(
        Group(notes, Text(""), examples),
        title="[bold cyan]Start Here[/bold cyan]",
        border_style="cyan",
    )


def _summarize_plan_progress(workspace: str) -> str:
    plan_text = memory.load_plan(workspace)
    if not plan_text:
        return "No active plan"
    done = plan_text.count("- [x]")
    pending = plan_text.count("- [ ]")
    total = done + pending
    if total == 0:
        return "Plan loaded"
    return f"{done}/{total} done"


def _format_session_usage(total_tokens: int, auto_compact_threshold: int) -> str:
    pct = min(100, int(total_tokens / max(auto_compact_threshold, 1) * 100))
    return f"{total_tokens:,} tokens ({pct}% of compact threshold)"


def _describe_last_change(workspace: str) -> str:
    change_set = memory.load_last_change_set(workspace)
    if not change_set:
        return "None"
    entries = change_set.get("entries") or []
    recorded_at = change_set.get("recorded_at", "recently")
    return f"{len(entries)} step{'s' if len(entries) != 1 else ''} recorded at {recorded_at}"


def _summarize_background_tasks() -> str:
    tasks = shell_agent.list_background_tasks()
    if not tasks:
        return "None"
    running = sum(1 for task in tasks if task.status == "running")
    finished = len(tasks) - running
    return f"{running} running · {finished} finished"


def _build_model_reply(model: str, codegen_model: str, *, cloud_codegen_enabled: bool) -> str:
    codegen_value = codegen_model if cloud_codegen_enabled else f"{model} (local fallback)"
    mode = "Cloud-assisted code generation" if cloud_codegen_enabled else "Local-only"
    return (
        "## Active models\n\n"
        f"- **Chat / routing:** `{model}`\n"
        f"- **Code generation:** `{codegen_value}`\n"
        f"- **Mode:** {mode}\n\n"
        "Use `/model list` to inspect installed local models or `/model remove <name>` to delete one."
    )


def _build_mode_reply(session_mode: str) -> str:
    return (
        "## Session mode\n\n"
        f"- **Current mode:** `{session_mode}`\n"
        f"- **Behavior:** {_mode_summary(session_mode)}\n\n"
        "Available modes: `read-only`, `plan`, `approve`, `auto`."
    )


def _build_reasoning_reply(show_reasoning: bool) -> str:
    state = "shown" if show_reasoning else "hidden"
    return (
        "## Reasoning display\n\n"
        f"- **Current setting:** `{state}`\n"
        "- **Behavior:** raw `<think>` output stays hidden by default; short task and plan panels remain visible."
    )


def _build_status_reply(
    workspace: str,
    model: str,
    codegen_model: str,
    *,
    cloud_codegen_enabled: bool,
    session_mode: str,
    show_reasoning: bool,
    total_tokens: int,
    auto_compact_threshold: int,
    num_ctx: int,
) -> str:
    state = _detect_project_state(
        workspace,
        has_memory=bool(memory.load_context(workspace)),
        has_plan=bool(memory.load_plan(workspace)),
    )
    session_meta = session_agent.ensure_session(workspace)
    shell_cwd = shell_agent.get_cwd()
    approval_mode = _mode_summary(session_mode)
    return (
        "## Session status\n\n"
        f"- **Session:** `{session_meta.get('name', pathlib.Path(workspace).resolve().name)}`\n"
        f"- **Workspace:** `{state['workspace_path']}`\n"
        f"- **Shell cwd:** `{shell_cwd}`\n"
        f"- **Entrypoint:** `{state['entrypoint'] or 'Not detected yet'}`\n"
        f"- **Plan:** {_summarize_plan_progress(workspace)}\n"
        f"- **Brainstorm notes:** {'Saved' if memory.load_brainstorm(workspace) else 'None yet'}\n"
        f"- **Memory:** {'Loaded' if state['has_memory'] else 'Not loaded yet'}\n"
        f"- **Session mode:** `{session_mode}`\n"
        f"- **Reasoning display:** {'shown' if show_reasoning else 'hidden'}\n"
        f"- **Models:** chat `{model}` · codegen "
        f"`{codegen_model if cloud_codegen_enabled else model}`\n"
        f"- **Context settings:** `{num_ctx:,}` max · compact at `{auto_compact_threshold:,}`\n"
        f"- **Session usage:** {_format_session_usage(total_tokens, auto_compact_threshold)}\n"
        f"- **Behavior:** {approval_mode}\n"
        f"- **Background tasks:** {_summarize_background_tasks()}\n"
        f"- **Git:** {_build_git_summary(workspace)}\n"
        f"- **Commit readiness:** {_build_commit_readiness(workspace)}\n"
        f"- **Last undoable change:** {_describe_last_change(workspace)}"
    )


def _build_history_reply(workspace: str, limit: int = 5) -> str:
    entries = memory.load_recent_activity(workspace, limit=limit)
    if not entries:
        return "No saved history yet."

    lines = ["## Recent history", ""]
    for entry in entries:
        stamp = " ".join(part for part in (entry.get("date"), entry.get("time")) if part)
        lines.append(f"- **{stamp}**")
        lines.append(f"  - **You:** {entry.get('user', '')}")
        lines.append(f"  - **CodeMitra:** {entry.get('assistant', '')}")
    return "\n".join(lines)


def _build_model_inventory_reply(
    active_model: str,
    codegen_model: str,
    *,
    cloud_codegen_enabled: bool,
    model_inventory: list | None = None,
) -> str:
    inventory = model_inventory if model_inventory is not None else config.get_local_model_inventory()
    total_ram_gib = config.get_total_system_memory_gib()
    budget_gib = config.get_recommended_model_budget_gib()
    lines = [
        "## Local models",
        "",
        f"- **Active chat model:** `{active_model}`",
        f"- **Active codegen model:** `{codegen_model if cloud_codegen_enabled else active_model}`",
    ]
    if total_ram_gib is not None:
        lines.append(f"- **Detected system RAM:** `{total_ram_gib:.1f} GB`")
    if budget_gib is not None:
        lines.append(f"- **Recommended local model budget:** `{budget_gib:.1f} GB`")
    lines.append("")

    normalized_inventory = []
    for item in inventory:
        if isinstance(item, str):
            normalized_inventory.append({"name": item, "size_text": "", "recommended": True})
            continue
        normalized_inventory.append(
            {
                "name": getattr(item, "name", ""),
                "size_text": getattr(item, "size_text", ""),
                "recommended": bool(getattr(item, "recommended", True)),
            }
        )

    recommended = [item for item in normalized_inventory if item["recommended"]]
    hidden = [item for item in normalized_inventory if not item["recommended"]]

    if not normalized_inventory:
        lines.append("No local Ollama models found.")
    else:
        if recommended:
            lines.append("### Recommended on this hardware")
            lines.append("")
            for item in recommended:
                suffix = " **(active)**" if item["name"] == active_model else ""
                size = f" - {item['size_text']}" if item["size_text"] else ""
                lines.append(f"- `{item['name']}`{suffix}{size}")
            lines.append("")
        if hidden:
            lines.append("### Hidden because they exceed the recommended budget")
            lines.append("")
            for item in hidden:
                suffix = " **(active)**" if item["name"] == active_model else ""
                size = f" - {item['size_text']}" if item["size_text"] else ""
                lines.append(f"- `{item['name']}`{suffix}{size}")
            lines.append("")

    lines.append("Use `/model remove <name>` to delete a local model and free space.")
    return "\n".join(lines)


def _handle_model_command(
    raw_input: str,
    active_model: str,
    codegen_model: str,
    *,
    cloud_codegen_enabled: bool,
) -> str:
    parts = raw_input.strip().split(maxsplit=2)
    if len(parts) == 1:
        return _build_model_reply(active_model, codegen_model, cloud_codegen_enabled=cloud_codegen_enabled)

    action = parts[1].lower()
    if action in {"list", "ls"}:
        return _build_model_inventory_reply(
            active_model,
            codegen_model,
            cloud_codegen_enabled=cloud_codegen_enabled,
        )

    if action in {"remove", "rm", "delete"}:
        if len(parts) < 3 or not parts[2].strip():
            return "Usage: `/model remove <name>`."
        target = parts[2].strip()
        if target == active_model:
            return f"Cannot remove the active chat model `{active_model}` while this session is using it."
        success, detail = config.remove_local_model(target)
        if not success:
            return f"Could not remove `{target}`.\n\n{detail}"
        inventory = _build_model_inventory_reply(
            active_model,
            codegen_model,
            cloud_codegen_enabled=cloud_codegen_enabled,
        )
        return f"{detail}\n\n{inventory}"

    return "Usage: `/model`, `/model list`, or `/model remove <name>`."


def _build_brainstorm_prompt(workspace: str, request: str) -> str:
    state = _detect_project_state(
        workspace,
        has_memory=bool(memory.load_context(workspace)),
        has_plan=bool(memory.load_plan(workspace)),
    )
    return (
        "You are CodeMitra in brainstorm mode.\n\n"
        "Behave like a strong product and engineering brainstorming partner.\n"
        "Use natural English with clean word order.\n"
        "Be warm, practical, and idea-focused.\n"
        "Start with a 1-2 sentence takeaway.\n"
        "Then use this structure when it fits:\n"
        "## Strong ideas\n"
        "1. Idea name - why it matters\n"
        "2. Idea name - why it matters\n"
        "## Recommended direction\n"
        "## Next steps\n"
        "Keep lists short and easy to scan.\n"
        "Do not use wide tables, side-by-side layouts, or overly long sections.\n"
        "If helpful, recommend one direction and explain why.\n"
        "Do not mention tools, agents, or system prompts.\n"
        "Do not sound robotic.\n\n"
        f"Workspace: {state['workspace_name']}\n"
        f"Entrypoint: {state['entrypoint'] or 'none detected'}\n"
        f"Plan loaded: {'yes' if state['has_plan'] else 'no'}\n"
        f"User request: {request}"
    )


def _run_brainstorm_reply(llm, workspace: str, request: str) -> str:
    response = llm.invoke([
        SystemMessage(content=_build_brainstorm_prompt(workspace, request)),
        HumanMessage(content=request),
    ])
    return (response.content or "").strip()


def _save_brainstorm_reply(workspace: str, prompt: str, reply: str) -> str:
    memory.append_brainstorm_entry(workspace, prompt, reply)
    return reply + "\n\n_Saved in brainstorm notes._"


def _is_git_repo(workspace: str) -> bool:
    result = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=workspace,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0 and result.stdout.strip() == "true"


def _git_output(workspace: str, args: list[str]) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=workspace,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return ""
    return (result.stdout or "").strip()


def _parse_git_status_counts(status_text: str) -> dict[str, int]:
    """Count staged, unstaged, and untracked entries from git status --short."""
    lines = [line for line in status_text.splitlines() if line.strip()]
    return {
        "staged": sum(1 for line in lines if not line.startswith("??") and line[0] != " "),
        "unstaged": sum(1 for line in lines if not line.startswith("??") and len(line) > 1 and line[1] != " "),
        "untracked": sum(1 for line in lines if line.startswith("??")),
        "total": len(lines),
    }


def _build_git_summary(workspace: str) -> str:
    """Return a compact branch-aware git summary for operator status surfaces."""
    if not _is_git_repo(workspace):
        return "Not a git repository"

    branch = _git_output(workspace, ["rev-parse", "--abbrev-ref", "HEAD"]) or "unknown"
    if branch == "HEAD":
        commit = _git_output(workspace, ["rev-parse", "--short", "HEAD"])
        branch = f"detached at {commit}" if commit else "detached HEAD"

    upstream = _git_output(workspace, ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"])
    counts = _parse_git_status_counts(_git_output(workspace, ["status", "--short"]))
    if counts["total"] == 0:
        state = "clean"
    else:
        parts = []
        if counts["staged"]:
            parts.append(f"{counts['staged']} staged")
        if counts["unstaged"]:
            parts.append(f"{counts['unstaged']} unstaged")
        if counts["untracked"]:
            parts.append(f"{counts['untracked']} untracked")
        state = ", ".join(parts) if parts else f"{counts['total']} changed"

    upstream_text = f" · upstream `{upstream}`" if upstream else ""
    return f"`{branch}`{upstream_text} · {state}"


def _build_commit_readiness(workspace: str) -> str:
    """Return a deterministic commit-readiness summary from git status."""
    if not _is_git_repo(workspace):
        return "Not a git repository"

    counts = _parse_git_status_counts(_git_output(workspace, ["status", "--short"]))
    if counts["total"] == 0:
        return "Clean working tree; nothing to commit"
    if counts["staged"] == 0:
        pending = counts["unstaged"] + counts["untracked"]
        return f"Not ready: no staged changes ({pending} unstaged/untracked)"
    if counts["unstaged"] == 0 and counts["untracked"] == 0:
        return f"Ready: {counts['staged']} staged change{'s' if counts['staged'] != 1 else ''}"

    leftovers = []
    if counts["unstaged"]:
        leftovers.append(f"{counts['unstaged']} unstaged")
    if counts["untracked"]:
        leftovers.append(f"{counts['untracked']} untracked")
    return (
        f"Partially ready: {counts['staged']} staged, "
        f"{' and '.join(leftovers)} outside the commit"
    )


def _truncate_diff(text: str, max_lines: int = 160) -> str:
    lines = text.splitlines()
    if len(lines) <= max_lines:
        return text
    kept = "\n".join(lines[:max_lines])
    return f"{kept}\n... ({len(lines) - max_lines} more lines omitted)"


def _render_change_entry_diff(entry: dict, workspace: str) -> str:
    kind = entry.get("kind")
    if kind == "move_file":
        src = pathlib.Path(entry["src"])
        dest = pathlib.Path(entry["dest"])
        try:
            src_display = f".\\{src.relative_to(workspace)}"
            dest_display = f".\\{dest.relative_to(workspace)}"
        except ValueError:
            src_display = str(src)
            dest_display = str(dest)
        return f"- moved `{src_display}` -> `{dest_display}`"

    path = pathlib.Path(entry["path"])
    try:
        display = f".\\{path.relative_to(workspace)}"
    except ValueError:
        display = str(path)

    before = (entry.get("before") or "").splitlines()
    after = (entry.get("after") or "").splitlines()
    if kind == "delete_file":
        after = []
    diff = "\n".join(
        difflib.unified_diff(
            before,
            after,
            fromfile=f"before\\{path.name}",
            tofile=f"after\\{path.name}",
            lineterm="",
        )
    )
    if not diff:
        return f"- changed `{display}`"
    return f"### `{display}`\n```diff\n{diff}\n```"


def _build_change_set_diff_reply(workspace: str) -> str | None:
    change_set = memory.load_last_change_set(workspace)
    if not change_set:
        return None

    entries = change_set.get("entries") or []
    if not entries:
        return None

    lines = ["## Last CodeMitra change set", ""]
    for entry in entries:
        lines.append(_render_change_entry_diff(entry, workspace))
        lines.append("")
    return "\n".join(lines).strip()


def _build_diff_reply(workspace: str) -> str:
    if _is_git_repo(workspace):
        diff_output = filesystem.git_diff.invoke({"cwd": workspace, "staged": False})
        if isinstance(diff_output, str) and diff_output.startswith("✓ git diff"):
            body = diff_output.split("\n", 1)[1] if "\n" in diff_output else "(no diff)"
            if body.strip() != "(no diff)":
                return f"## Working tree diff\n\n```diff\n{_truncate_diff(body)}\n```"

    change_set_reply = _build_change_set_diff_reply(workspace)
    if change_set_reply:
        return change_set_reply

    return "No diff is available yet."


def _build_change_set_review_input(workspace: str) -> str | None:
    change_set = memory.load_last_change_set(workspace)
    if not change_set:
        return None

    entries = change_set.get("entries") or []
    if not entries:
        return None

    lines = ["Last CodeMitra change set", ""]
    for entry in entries:
        kind = entry.get("kind")
        if kind == "move_file":
            src = pathlib.Path(entry["src"])
            dest = pathlib.Path(entry["dest"])
            try:
                src_display = f".\\{src.relative_to(workspace)}"
                dest_display = f".\\{dest.relative_to(workspace)}"
            except ValueError:
                src_display = str(src)
                dest_display = str(dest)
            lines.append(f"- moved {src_display} -> {dest_display}")
            continue

        path = pathlib.Path(entry["path"])
        try:
            display = f".\\{path.relative_to(workspace)}"
        except ValueError:
            display = str(path)
        lines.append(f"File: {display}")
        lines.append(_render_change_entry_diff(entry, workspace))
        lines.append("")

    return "\n".join(lines).strip()


def _parse_review_target(raw: str) -> str:
    remainder = raw.strip()[7:].strip().lower()
    if remainder == "staged":
        return "staged"
    return "working"


def _build_git_review_input(workspace: str, *, staged: bool) -> tuple[str, str] | None:
    status_output = filesystem.git_status.invoke({"cwd": workspace})
    diff_output = filesystem.git_diff.invoke({"cwd": workspace, "staged": staged})
    if not (isinstance(diff_output, str) and diff_output.startswith("✓ git diff")):
        return None

    body = diff_output.split("\n", 1)[1] if "\n" in diff_output else ""
    if not body.strip() or body.strip() == "(no diff)":
        return None

    status_body = ""
    if isinstance(status_output, str) and status_output.startswith("✓ git status"):
        status_body = status_output.split("\n", 1)[1] if "\n" in status_output else ""

    label = "staged git diff" if staged else "current git diff"
    review_input = (
        f"Git status:\n{status_body or '(nothing to report)'}\n\n"
        f"Diff:\n{_truncate_diff(body, max_lines=220)}"
    )
    return (label, review_input)


def _get_review_material(workspace: str, target: str = "working") -> tuple[str, str] | None:
    if _is_git_repo(workspace):
        git_material = _build_git_review_input(workspace, staged=(target == "staged"))
        if git_material is not None:
            return git_material

    change_set_input = _build_change_set_review_input(workspace)
    if change_set_input:
        return ("last CodeMitra change set", change_set_input)

    return None


def _cmd_review(workspace: str, llm, target: str = "working") -> str:
    material = _get_review_material(workspace, target=target)
    if material is None:
        return "Nothing to review yet. Make a change first or use `/diff` to inspect the current state."

    source, review_input = material
    response = reviewer_agent.run(
        llm,
        "Review the current changes and surface any material issues.",
        review_input,
        source=source,
    )
    console.print(reviewer_agent.render(response))
    return response.summary


def _cmd_resume(workspace: str) -> str:
    reply = session_agent.build_resume_reply(workspace)
    console.print(session_agent.render_resume(reply))
    return reply


def _cmd_rename(raw: str, workspace: str) -> str:
    new_name = raw.strip()[7:].strip()
    if not new_name:
        metadata = session_agent.ensure_session(workspace)
        return f"Current session name: `{metadata.get('name', pathlib.Path(workspace).resolve().name)}`"

    updated = session_agent.rename_session(workspace, new_name)
    return f"Renamed the current session to `{updated.get('name', new_name)}`."


def _cmd_explain(raw: str, workspace: str, llm) -> str:
    target = raw.strip()[8:].strip()
    if not target:
        return "Usage: `/explain <file>`"

    response = explainer_agent.run(llm, workspace, target)
    console.print(explainer_agent.render(response))
    return response.summary


def _cmd_symbols(raw: str, workspace: str) -> str:
    symbol = raw.strip()[8:].strip()
    if not symbol:
        return "Usage: `/symbols <name>`"

    response = codeintel_agent.run(workspace, symbol)
    console.print(codeintel_agent.render(response))
    return response.summary


def _cmd_search(raw: str, llm) -> str:
    query = raw.strip()[7:].strip()
    if not query:
        return "Usage: `/search <query>`"

    response = web_agent.run(llm, f"Search the web for: {query}", console=console)
    console.print(web_agent.render(response))
    return response.summary


def _cmd_open_url(raw: str, llm) -> str:
    target = raw.strip()[9:].strip()
    if not target:
        return "Usage: `/open-url <url>`"

    response = web_agent.run(llm, f"Read and summarize this page: {target}", console=console)
    console.print(web_agent.render(response))
    return response.summary


def _find_cleanup_candidates(workspace: str) -> list[str]:
    root = pathlib.Path(workspace)
    candidates: list[str] = []
    for current_root, dirnames, filenames in os.walk(root, topdown=True, followlinks=False):
        current = pathlib.Path(current_root)
        if ".venv" in dirnames:
            dirnames.remove(".venv")
        if ".git" in dirnames:
            dirnames.remove(".git")
        for dirname in list(dirnames):
            if dirname.lower() in _CLEANUP_NAME_HINTS:
                rel = current.joinpath(dirname).relative_to(root)
                candidates.append(str(rel))
                dirnames.remove(dirname)
        for filename in filenames:
            lowered = filename.lower()
            if lowered.endswith((".pyc", ".pyo")) or lowered in {"thumbs.db"}:
                rel = current.joinpath(filename).relative_to(root)
                candidates.append(str(rel))
    return sorted(dict.fromkeys(candidates))


def _looks_like_project_root(path: pathlib.Path) -> bool:
    return any(
        (path / marker).exists()
        for marker in ("pyproject.toml", "requirements.txt", "package.json", ".git", "README.md")
    )


def _resolve_cleanup_root(workspace: str, user_input: str) -> pathlib.Path | None:
    root = pathlib.Path(workspace)
    normalized = re.sub(r"\s+", " ", user_input.strip().lower())
    top_level_dirs = [entry for entry in root.iterdir() if entry.is_dir() and not entry.name.startswith(".")]

    for entry in sorted(top_level_dirs, key=lambda p: len(p.name), reverse=True):
        name = entry.name.lower()
        if name in normalized or name.replace("-", " ") in normalized or name.replace("_", " ") in normalized:
            return entry

    if _looks_like_project_root(root):
        return root

    if len(top_level_dirs) == 1:
        return top_level_dirs[0]

    return None


def _build_cleanup_preview(workspace: str, candidates: list[str]) -> str:
    if not candidates:
        return (
            "I do not see any obvious cleanup targets in this workspace.\n\n"
            "If you want something removed, tell me the exact folder or file name and I will preview it first."
        )
    preview = "\n".join(f"- `{path}`" for path in candidates[:12])
    if len(candidates) > 12:
        preview += f"\n- `...and {len(candidates) - 12} more`"
    return (
        "I found these likely cleanup targets and will leave source code, `.venv`, and project config alone unless you ask otherwise:\n\n"
        f"{preview}"
    )


def _choose_approval_option(
    title: str,
    prompt: str,
    options: list[tuple[str, str]],
    *,
    fallback_default: str | None = None,
) -> str | None:
    try:
        return radiolist_dialog(
            title=title,
            text=prompt,
            values=options,
            ok_text="Select",
            cancel_text="Cancel",
        ).run()
    except Exception:
        pass

    console.print()
    lines = [prompt, ""]
    for index, (_, label) in enumerate(options, 1):
        lines.append(f"{index}. {label}")
    lines.append("")
    lines.append("Enter a number to choose. Press Enter for the default option.")
    console.print(
        Panel(
            "\n".join(lines),
            title=f"[bold yellow]{title}[/bold yellow]",
            border_style="yellow",
            padding=(0, 2),
        )
    )
    try:
        answer = console.input("  ").strip()
    except (EOFError, KeyboardInterrupt):
        return None
    if not answer:
        return fallback_default
    if answer.isdigit():
        index = int(answer) - 1
        if 0 <= index < len(options):
            return options[index][0]
    return None


def _print_approval_result(message: str, *, approved: bool) -> None:
    style = "[green]✔[/green]" if approved else "[red]✘[/red]"
    console.print(f"  {style} {message}")


def _shell_command_name(command: str) -> str:
    try:
        parts = shell_agent._split_command(command)
    except ValueError:
        parts = command.strip().split()
    if not parts:
        return command.strip().lower()
    exe = pathlib.Path(parts[0]).name
    return re.sub(r"\.exe$", "", exe, flags=re.IGNORECASE).lower()


def _confirm_cleanup_plan(candidates: list[str]) -> bool:
    preview = "\n".join(f"• {path}" for path in candidates[:10])
    if len(candidates) > 10:
        preview += f"\n• ...and {len(candidates) - 10} more"
    choice = _choose_approval_option(
        "Cleanup plan",
        "CodeMitra prepared a cleanup plan for obvious disposable folders/files.\n\n"
        f"{preview}\n\nChoose what to do next.",
        [
            ("deny", "No, keep these files/folders"),
            ("approve", "Yes, apply this cleanup plan"),
        ],
        fallback_default="deny",
    )
    approved = choice == "approve"
    _print_approval_result("Approved" if approved else "Skipped", approved=approved)
    return approved


def _handle_cleanup_request(user_input: str, workspace: str) -> str:
    cleanup_root = _resolve_cleanup_root(workspace, user_input)
    if cleanup_root is None:
        return (
            "I need a specific folder before I clean anything here because this workspace contains multiple projects.\n\n"
            "Tell me the exact folder name you want cleaned, for example `snake-game`."
        )

    root_display = cleanup_root.name if cleanup_root != pathlib.Path(workspace) else "."
    relative_root = cleanup_root.relative_to(pathlib.Path(workspace)) if cleanup_root != pathlib.Path(workspace) else pathlib.Path(".")
    candidates = _find_cleanup_candidates(str(cleanup_root))
    candidates = [str(relative_root / candidate) if str(relative_root) != "." else candidate for candidate in candidates]
    preview = _build_cleanup_preview(workspace, candidates)
    _print_progress_message("Reviewing cleanup candidates", f"Target: `{root_display}`")
    console.print()
    console.print(Rule(style="dim"))
    console.print(
        Panel(
            Markdown(f"**Cleanup target:** `{root_display}`\n\n{preview}"),
            title="[bold cyan]CodeMitra[/bold cyan]",
            border_style="cyan",
        )
    )
    if not candidates:
        return f"Cleanup target: {root_display}\n\n{preview}"
    if not _confirm_cleanup_plan(candidates):
        return f"Proposed a cleanup plan for {root_display}, but did not remove anything."

    console.print()
    result = filesystem.execute_cleanup(candidates, request=user_input)
    console.print(render(result))
    return result.summary


def _build_run_command_reply(workspace: str) -> str:
    root = pathlib.Path(workspace)
    state = _detect_project_state(workspace)
    activate = ".\\.venv\\Scripts\\Activate.ps1"
    target = state["entrypoint"]

    run_cmd = f"python {target}" if target else "python <entrypoint>.py"

    lines = ["From PowerShell in this folder, run:", ""]
    step = 1
    if not state["venv_exists"]:
        lines.append(f"{step}. `python -m venv .venv`")
        step += 1
    lines.append(f"{step}. `{activate}`")
    step += 1

    if state["dependency_source"] == "requirements.txt":
        lines.append(f"{step}. `pip install -r .\\requirements.txt`")
        step += 1
    elif state["dependency_source"] == "pyproject.toml":
        lines.append(f"{step}. `pip install -e .`")
        step += 1
    elif state["dependency_source"] == "package.json":
        lines.append(f"{step}. `npm install`")
        step += 1

    lines.append(f"{step}. `{run_cmd}`")

    return "\n".join(lines)


def _confirm_plan_start() -> bool:
    """Ask whether the newly generated plan should start executing immediately."""
    choice = _choose_approval_option(
        "Start execution",
        "Plan ready.\n\nStart with step 1 now?",
        [
            ("approve", "Yes, start with step 1 now"),
            ("deny", "No, pause after planning"),
        ],
        fallback_default="approve",
    )
    approved = choice == "approve"
    _print_approval_result(
        "Starting step 1" if approved else "Paused after planning",
        approved=approved,
    )
    return approved


def _execute_approved_plan(
    *,
    workspace: str,
    llm,
    max_steps: int | None,
    session_mode: str = "approve",
    codegen_llm=None,
    reader_llm=None,
    shell_llm=None,
    direct_llm=None,
) -> str:
    if _normalize_session_mode(session_mode) in {"read-only", "plan"}:
        return _build_plan_execution_blocked_reply(session_mode, active_plan=True)
    if not planner_agent.is_plan_approved(workspace):
        return _build_plan_unapproved_reply()
    return planner_agent.run_plan(
        llm,
        workspace,
        console=console,
        max_steps=max_steps,
        codegen_llm=codegen_llm,
        reader_llm=reader_llm,
        shell_llm=shell_llm,
        direct_llm=direct_llm,
    )


def _auto_plan_request(
    raw: str,
    workspace: str,
    llm,
    *,
    session_mode: str = "approve",
    codegen_llm=None,
    reader_llm=None,
    shell_llm=None,
    direct_llm=None,
) -> str:
    """Run brainstorm + plan for a substantial request, then optionally start execution."""
    from app.agents import brainstorm as brainstorm_agent

    goal = raw.strip()
    _print_progress_message("Brainstorming the request", "I’m shaping the goal before writing a plan.", color="yellow")
    context = brainstorm_agent.run(llm, goal, console)
    _print_progress_message("Writing the plan", "Saving the next steps to `.codemitra/plan.md`.", color="yellow")
    with console.status("[bold green]Generating plan...[/bold green]"):
        plan = planner_agent.create_plan(llm, goal, workspace, context=context)
    console.print(f"[dim cyan]  ✦  Plan written to .codemitra/plan.md[/dim cyan]")
    console.print(planner_agent.render(plan))

    if _normalize_session_mode(session_mode) in {"read-only", "plan"}:
        console.print("[dim]Plan mode is active, so CodeMitra saved the plan without starting execution.[/dim]")
        return f"Created a plan for: {goal}"

    if _confirm_plan_start():
        planner_agent.approve_plan(workspace)
        return _execute_approved_plan(
            workspace=workspace,
            llm=llm,
            max_steps=1,
            session_mode=session_mode,
            codegen_llm=codegen_llm,
            reader_llm=reader_llm,
            shell_llm=shell_llm,
            direct_llm=direct_llm,
        )

    console.print("[dim]Use [cyan]/plan approve[/cyan] when you're ready, then [cyan]/plan next[/cyan].[/dim]")
    return f"Created a plan for: {goal}"


def _pick_model(cfg: dict) -> str:
    """Return the model to use: from config if set, otherwise prompt the user."""
    configured = cfg.get("local_model") or cfg.get("model")
    if configured:
        console.print(f"[dim cyan]  ✔  Local model: {configured}[/dim cyan]")
        return configured

    while True:
        inventory = config.get_local_model_inventory()
        if not inventory:
            console.print("[red]No local Ollama models found. Run 'ollama pull <model>' first.[/red]")
            raise SystemExit(1)

        recommended_models = [model for model in inventory if model.recommended]
        hidden_models = [model for model in inventory if not model.recommended]
        visible_models = recommended_models or inventory
        total_ram_gib = config.get_total_system_memory_gib()
        budget_gib = config.get_recommended_model_budget_gib()

        console.print("\n[bold cyan]Recommended models for this hardware:[/bold cyan]")
        if total_ram_gib is not None and budget_gib is not None:
            console.print(
                f"[dim]Detected RAM: {total_ram_gib:.1f} GB  ·  Recommended local model budget: {budget_gib:.1f} GB[/dim]"
            )
        if not recommended_models:
            console.print("[yellow]No installed model fits the recommended budget right now, so CodeMitra is showing all installed models.[/yellow]")
        for i, model_info in enumerate(visible_models, 1):
            size = f" [dim]({model_info.size_text})[/dim]" if model_info.size_text else ""
            console.print(f"  [cyan]{i}[/cyan]  {model_info.name}{size}")
        if hidden_models:
            console.print("\n[dim]Hidden because they exceed the recommended budget:[/dim]")
            for model_info in hidden_models:
                size = f" ({model_info.size_text})" if model_info.size_text else ""
                console.print(f"  [dim]- {model_info.name}{size}[/dim]")
            console.print("[dim]Use `rm <name>` to delete hidden models and free space.[/dim]")
        console.print("[dim]Pick a number or name from the recommended list. Use `rm <number|name>` to delete one, or `refresh` to reload.[/dim]")

        choice = console.input("\n[bold]Pick a model (number or name):[/bold] ").strip()
        if not choice:
            console.print("[yellow]Pick a model name or number.[/yellow]")
            continue

        normalized = choice.lower()
        if normalized in {"refresh", "reload"}:
            continue

        if normalized.startswith(("rm ", "remove ", "delete ")):
            _, raw_target = choice.split(None, 1)
            target = raw_target.strip()
            if target.isdigit():
                idx = int(target) - 1
                if 0 <= idx < len(visible_models):
                    target = visible_models[idx].name
                else:
                    console.print("[yellow]Invalid model number to remove.[/yellow]")
                    continue
            elif target not in {model.name for model in inventory}:
                console.print("[yellow]Unknown model name to remove.[/yellow]")
                continue

            success, detail = config.remove_local_model(target)
            style = "green" if success else "red"
            console.print(f"[{style}]{detail}[/{style}]")
            continue

        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(visible_models):
                return visible_models[idx].name
        elif choice in {model.name for model in visible_models}:
            return choice
        elif choice in {model.name for model in hidden_models}:
            console.print("[yellow]That model is hidden because it exceeds this machine's recommended memory budget. Remove it or pick a smaller model.[/yellow]")
            continue
        console.print("[yellow]Invalid choice, try again.[/yellow]")


def _resolve_codegen_model(cfg: dict) -> str:
    """Return the cloud model to use for code generation when enabled."""
    return (cfg.get("codegen_model") or _DEFAULT_CLOUD_CODEGEN_MODEL).strip()


def _resolve_cloud_api_key(cfg: dict, prompt_fn=None) -> str:
    """Return API key from config/env or prompt once for optional cloud codegen."""
    configured = (cfg.get("ollama_api_key") or "").strip()
    if configured:
        return configured

    prompt_fn = prompt_fn or getpass.getpass
    console.print(
        "[dim]Optional: enter an Ollama API key to enable cloud code generation. "
        "Press Enter to stay local-only.[/dim]"
    )
    try:
        return (prompt_fn("Ollama API key (optional): ") or "").strip()
    except (EOFError, KeyboardInterrupt):
        return ""


def _print_hint_bar() -> None:
    """Single-line hint shown once after model selection."""
    console.print(
        "  [dim]/help[/dim][dim] commands  ·  [/dim]"
        "[dim]/status[/dim][dim]  ·  [/dim]"
        "[dim]/permissions[/dim][dim]  ·  [/dim]"
        "[dim]/tasks[/dim][dim]  ·  [/dim]"
        "[dim]/search[/dim][dim]  ·  [/dim]"
        "[dim]/hibernate[/dim][dim]  ·  [/dim]"
        "[dim]/run --background <cmd>[/dim][dim]  ·  [/dim]"
        "[dim]/plan <goal>[/dim][dim]  ·  [/dim]"
        "[dim]Tab[/dim][dim] to complete  ·  [/dim]"
        "[dim]↑↓[/dim][dim] history[/dim][dim]  ·  [/dim]"
        "[dim]Ctrl+G[/dim][dim] editor[/dim]"
    )
    console.print()


def _apply_session_mode(cfg: dict, session_mode: str) -> None:
    normalized = _normalize_session_mode(session_mode)
    read_only_tools = {"read_file", "list_directory", "git_status", "git_diff"}
    disabled_tools = {str(name) for name in (cfg.get("disabled_tools") or [])}
    disabled_commands = {str(name).lower() for name in (cfg.get("disabled_commands") or [])}
    allowed_roots = list(cfg.get("allowed_roots") or [])
    if normalized in {"read-only", "plan"}:
        allowed_tools = read_only_tools - disabled_tools
        confirm_tool = None
        require_diff = False
        shell_confirm = None
    elif normalized == "auto":
        allowed_tools = set(filesystem._DEFAULT_TOOLS) - disabled_tools
        confirm_tool = None
        require_diff = False
        shell_confirm = None
    else:
        allowed_tools = set(filesystem._DEFAULT_TOOLS) - disabled_tools
        confirm_tool = _confirm_tool
        require_diff = cfg.get("require_diff_approval", True)
        shell_confirm = _confirm_shell
    allowed_commands = {
        command for command in shell_agent._DEFAULT_COMMANDS
        if command.lower() not in disabled_commands
    }

    filesystem.configure(
        workspace=cfg["workspace"],
        allowed_roots=allowed_roots,
        allowed_tools=allowed_tools,
        allowed_commands=allowed_commands,
        confirm_fn=confirm_tool,
        require_diff_approval=require_diff,
    )
    reader_agent.configure(workspace=cfg["workspace"], allowed_roots=allowed_roots)
    shell_agent.configure(
        workspace=cfg["workspace"],
        allowed_roots=allowed_roots,
        session_mode=normalized,
        allowed_commands=allowed_commands,
        stream_to_console=True,
        confirm_fn=shell_confirm,
    )


def _chat():
    global _LAST_SHELL_COMMAND
    _clear_terminal()
    show_banner()

    cfg = config.load()
    model = _pick_model(cfg)
    codegen_model = _resolve_codegen_model(cfg)
    temperature = cfg.get("temperature", 0.2)
    session_mode = _normalize_session_mode(cfg.get("session_mode"))
    show_reasoning = bool(cfg.get("show_reasoning", False))
    num_ctx = int(cfg.get("num_ctx", 131072))

    _apply_session_mode(cfg, session_mode)

    # Build system prompt, appending project rules + memory context
    system_prompt = SYSTEM_PROMPT
    if cfg.get("rules"):
        system_prompt += f"\n\n## Project Rules (from CODEMITRA.md)\n{cfg['rules']}"
        console.print("[dim cyan]  ✦  Project rules loaded from CODEMITRA.md[/dim cyan]")

    project_instructions = cfg.get("project_instructions") or []
    instructions_prompt = _build_project_instructions_prompt(project_instructions)
    if instructions_prompt:
        system_prompt += f"\n\n{instructions_prompt}"
        count = len(project_instructions)
        console.print(f"[dim cyan]  ✦  Project instruction file{'s' if count != 1 else ''} loaded: {count}[/dim cyan]")

    available_skills = skills_registry.discover(cfg["workspace"], cfg.get("skill_dirs"))
    skills_prompt = _build_skills_prompt(available_skills)
    if skills_prompt:
        system_prompt += f"\n\n{skills_prompt}"
        count = len(available_skills)
        console.print(f"[dim cyan]  ✦  CodeMitra skill{'s' if count != 1 else ''} loaded: {count}[/dim cyan]")

    ctx_text = memory.load_context(cfg["workspace"])
    if ctx_text:
        system_prompt += f"\n\n## Project Memory (from .codemitra/context.md)\n{ctx_text}"
        console.print("[dim cyan]  ✦  Project memory loaded from .codemitra/context.md[/dim cyan]")

    startup_project_brief = _build_startup_project_brief(cfg["workspace"])
    if startup_project_brief:
        system_prompt += f"\n\n{startup_project_brief}"
        console.print("[dim cyan]  ✦  Startup project brief auto-detected from the workspace[/dim cyan]")

    plan_text = memory.load_plan(cfg["workspace"])
    if plan_text:
        system_prompt += f"\n\n## Active Plan (from .codemitra/plan.md)\n{plan_text}"
        console.print("[dim cyan]  ✦  Active plan loaded from .codemitra/plan.md[/dim cyan]")

    console.print(
        _build_startup_status(
            cfg["workspace"],
            has_memory=bool(ctx_text),
            has_plan=bool(plan_text),
            session_mode=session_mode,
            show_reasoning=show_reasoning,
            num_ctx=num_ctx,
            auto_compact_threshold=int(cfg.get("auto_compact_threshold", _AUTO_COMPACT_THRESHOLD)),
        )
    )
    console.print("[dim]Ask naturally, or use /help for the full command list.[/dim]")

    if ctx_text or plan_text:
        console.print()

    local_llm = get_local_llm(
        model,
        temperature,
        base_url=cfg.get("ollama_local_base_url"),
        num_ctx=num_ctx,
    )
    cloud_api_key = _resolve_cloud_api_key(cfg)
    codegen_llm = local_llm
    if cloud_api_key:
        codegen_llm = get_cloud_llm(
            codegen_model,
            temperature,
            api_key=cloud_api_key,
            base_url=cfg.get("ollama_cloud_base_url"),
            num_ctx=num_ctx,
        )
        console.print(
            f"[dim cyan]  ✦  Cloud codegen model: {codegen_model}[/dim cyan]"
        )
    else:
        console.print(
            "[dim]No Ollama API key provided. Code generation stays on the local model.[/dim]"
        )

    auto_compact_threshold = int(cfg.get("auto_compact_threshold", _AUTO_COMPACT_THRESHOLD))
    setup_tool   = filesystem.make_routing_tool(codegen_llm)
    shell_tool   = shell_agent.make_routing_tool(local_llm, console=console)
    reader_tool  = reader_agent.make_routing_tool(local_llm, console=console)
    planner_tool = planner_agent.make_routing_tool(
        local_llm,
        workspace=cfg["workspace"],
        console=console,
        codegen_llm=codegen_llm,
        reader_llm=local_llm,
        shell_llm=local_llm,
        direct_llm=local_llm,
    )
    web_tool = web_agent.make_routing_tool(local_llm, console=console)
    main_llm = local_llm.bind_tools([setup_tool, shell_tool, reader_tool, planner_tool, web_tool])

    # ── Hint bar + prompt setup ───────────────────────────────────────────────
    _print_hint_bar()
    prompt_str = _build_prompt_label(model, session_mode)
    completer = _make_completer(cfg["workspace"])
    current_task = "Ready"

    def _set_current_task(label: str) -> None:
        nonlocal current_task
        current_task = label or "Ready"

    session = PromptSession(
        history=InMemoryHistory(),
        completer=completer,
        key_bindings=_make_key_bindings(),
        bottom_toolbar=lambda: _build_bottom_toolbar(
            session_mode=session_mode,
            model=model,
            cwd=shell_agent.get_cwd(),
            total_tokens=sess_in + sess_out,
            auto_compact_threshold=auto_compact_threshold,
            current_task=current_task,
            background_tasks=shell_agent.count_background_tasks(only_running=True),
        ),
    )
    messages = [SystemMessage(content=system_prompt)]
    sess_in = sess_out = 0  # cumulative session token counts

    while True:
        _set_current_task("Ready")
        user_input = session.prompt(prompt_str)

        if user_input.strip() in ["/exit", "exit", "quit"]:
            console.print("[yellow]Goodbye.[/yellow]")
            break

        if not user_input.strip():
            continue

        if _is_bang_command(user_input):
            bang_command = _extract_bang_command(user_input)
            _set_current_task(f"Running {bang_command}")
            _cmd_run(bang_command)
            continue

        navigation_target = (
            _extract_navigation_target(user_input)
            or _extract_workspace_selection_target(user_input, shell_agent.get_cwd())
        )
        if navigation_target:
            _cmd_run(f"cd {navigation_target}")
            if _is_project_summary_request(user_input) or _is_understand_alias_request(user_input):
                ai_reply = _build_project_summary(shell_agent.get_cwd())
                console.print()
                console.print(Rule(style="dim"))
                console.print(
                    Panel(
                        Markdown(ai_reply),
                        title="[bold cyan]CodeMitra[/bold cyan]",
                        border_style="cyan",
                    )
                )
                memory.append_activity(cfg["workspace"], user_input, ai_reply)
                memory.update_context(cfg["workspace"], user_input)
            continue

        normalized_input = re.sub(r"\s+", " ", user_input.strip().lower())
        if (
            session_mode in {"read-only", "plan"}
            and normalized_input in {"continue", "next step", "proceed", "keep going", "execute the plan"}
        ):
            ai_reply = _build_plan_execution_blocked_reply(session_mode)
            console.print()
            console.print(Rule(style="dim"))
            console.print(
                Panel(
                    Markdown(ai_reply),
                    title="[bold cyan]CodeMitra[/bold cyan]",
                    border_style="cyan",
                )
            )
            memory.append_activity(cfg["workspace"], user_input, ai_reply)
            memory.update_context(cfg["workspace"], user_input)
            continue
        if (
            normalized_input in {"continue", "next step", "proceed", "keep going", "execute the plan"}
            and memory.load_plan(cfg["workspace"])
            and not planner_agent.is_plan_approved(cfg["workspace"])
        ):
            ai_reply = _build_plan_unapproved_reply()
            console.print()
            console.print(Rule(style="dim"))
            console.print(
                Panel(
                    Markdown(ai_reply),
                    title="[bold cyan]CodeMitra[/bold cyan]",
                    border_style="cyan",
                )
            )
            memory.append_activity(cfg["workspace"], user_input, ai_reply)
            memory.update_context(cfg["workspace"], user_input)
            continue

        web_query = _extract_web_search_query(user_input)
        if web_query:
            _set_current_task("Searching the web")
            _print_progress_message("Searching the web", web_query[:120], color="cyan")
            ai_reply = _cmd_search(f"/search {web_query}", local_llm)
            memory.append_activity(cfg["workspace"], user_input, ai_reply)
            memory.update_context(cfg["workspace"], user_input)
            continue

        requested_url = _extract_url_from_input(user_input)
        if requested_url and (
            normalized_input == requested_url.lower()
            or any(hint in normalized_input for hint in ("read", "open", "page", "url", "website", "site", "summarize"))
        ):
            _set_current_task("Reading webpage")
            _print_progress_message("Reading the webpage", requested_url[:120], color="cyan")
            ai_reply = _cmd_open_url(f"/open-url {requested_url}", local_llm)
            memory.append_activity(cfg["workspace"], user_input, ai_reply)
            memory.update_context(cfg["workspace"], user_input)
            continue

        intent = _classify_intent(user_input)
        progress_note = _build_intent_progress_message(intent, user_input)
        if progress_note:
            _set_current_task(progress_note[0])
            _print_progress_message(*progress_note)

        if intent == "chat" and _is_simple_greeting(user_input):
            console.print()
            console.print(Rule(style="dim"))
            console.print(
                Panel(
                    Markdown(_build_greeting_reply()),
                    title="[bold cyan]CodeMitra[/bold cyan]",
                    border_style="cyan",
                )
            )
            continue

        if intent == "chat" and _is_small_talk(user_input):
            ai_reply = _build_small_talk_reply(user_input)
            console.print()
            console.print(Rule(style="dim"))
            console.print(
                Panel(
                    Markdown(ai_reply),
                    title="[bold cyan]CodeMitra[/bold cyan]",
                    border_style="cyan",
                )
            )
            memory.append_activity(cfg["workspace"], user_input, ai_reply)
            memory.update_context(cfg["workspace"], user_input)
            continue

        if intent == "brainstorm":
            ai_reply = _save_brainstorm_reply(
                cfg["workspace"],
                user_input,
                _run_brainstorm_reply(local_llm, cfg["workspace"], user_input),
            )
            console.print()
            console.print(Rule(style="dim"))
            console.print(
                Panel(
                    Markdown(ai_reply),
                    title="[bold cyan]CodeMitra[/bold cyan]",
                    border_style="cyan",
                )
            )
            memory.append_activity(cfg["workspace"], user_input, ai_reply)
            memory.update_context(cfg["workspace"], user_input)
            continue

        if intent == "explain" and _is_current_folder_request(user_input):
            ai_reply = _build_current_folder_reply(shell_agent.get_cwd(), workspace=cfg["workspace"])
            console.print()
            console.print(Rule(style="dim"))
            console.print(
                Panel(
                    Markdown(ai_reply),
                    title="[bold cyan]CodeMitra[/bold cyan]",
                    border_style="cyan",
                )
            )
            memory.append_activity(cfg["workspace"], user_input, ai_reply)
            memory.update_context(cfg["workspace"], user_input)
            continue

        if intent == "explain" and _is_understand_alias_request(user_input):
            ai_reply = _build_project_summary(shell_agent.get_cwd())
            console.print()
            console.print(Rule(style="dim"))
            console.print(
                Panel(
                    Markdown(ai_reply),
                    title="[bold cyan]CodeMitra[/bold cyan]",
                    border_style="cyan",
                )
            )
            memory.append_activity(cfg["workspace"], user_input, ai_reply)
            memory.update_context(cfg["workspace"], user_input)
            continue

        if intent == "explain" and _is_project_summary_request(user_input):
            ai_reply = _build_project_summary(shell_agent.get_cwd())
            console.print()
            console.print(Rule(style="dim"))
            console.print(
                Panel(
                    Markdown(ai_reply),
                    title="[bold cyan]CodeMitra[/bold cyan]",
                    border_style="cyan",
                )
            )
            memory.append_activity(cfg["workspace"], user_input, ai_reply)
            memory.update_context(cfg["workspace"], user_input)
            continue

        if intent == "change" and _is_cleanup_request(user_input):
            ai_reply = _handle_cleanup_request(user_input, shell_agent.get_cwd())
            memory.append_activity(cfg["workspace"], user_input, ai_reply)
            memory.update_context(cfg["workspace"], user_input)
            continue

        if _is_delete_project_request(user_input):
            ai_reply = _build_root_delete_reply(cfg["workspace"])
            console.print()
            console.print(Rule(style="dim"))
            console.print(
                Panel(
                    Markdown(ai_reply),
                    title="[bold cyan]CodeMitra[/bold cyan]",
                    border_style="cyan",
                )
            )
            memory.append_activity(cfg["workspace"], user_input, ai_reply)
            memory.update_context(cfg["workspace"], user_input)
            continue

        if intent == "change":
            root_rename_reply = _build_root_rename_reply(user_input, cfg["workspace"])
            if root_rename_reply:
                console.print()
                console.print(Rule(style="dim"))
                console.print(
                    Panel(
                        Markdown(root_rename_reply),
                        title="[bold cyan]CodeMitra[/bold cyan]",
                        border_style="cyan",
                    )
                )
                memory.append_activity(cfg["workspace"], user_input, root_rename_reply)
                memory.update_context(cfg["workspace"], user_input)
                continue

        if intent == "run-help":
            ai_reply = _build_run_command_reply(cfg["workspace"])
            console.print()
            console.print(Rule(style="dim"))
            console.print(
                Panel(
                    Markdown(ai_reply),
                    title="[bold cyan]CodeMitra[/bold cyan]",
                    border_style="cyan",
                )
            )
            memory.append_activity(cfg["workspace"], user_input, ai_reply)
            memory.update_context(cfg["workspace"], user_input)
            continue

        if intent == "plan":
            ai_reply = _auto_plan_request(
                user_input,
                cfg["workspace"],
                local_llm,
                session_mode=session_mode,
                codegen_llm=codegen_llm,
                reader_llm=local_llm,
                shell_llm=local_llm,
                direct_llm=local_llm,
            )
            if ai_reply:
                memory.append_activity(cfg["workspace"], user_input, ai_reply)
                memory.update_context(cfg["workspace"], user_input)
            continue

        # ── Slash commands ────────────────────────────────────────────────────
        cmd = user_input.strip().lower()

        if cmd in ("/help", "help"):
            _print_help()
            continue

        if cmd in ("/reset", "reset"):
            messages = [SystemMessage(content=system_prompt)]
            console.print("[dim]Session reset.[/dim]")
            continue

        if cmd in ("/init", "codemitra init"):
            _run_init()
            continue

        if cmd.startswith("/plan"):
            ai_reply = _cmd_plan(
                user_input,
                cfg["workspace"],
                llm=local_llm,
                session_mode=session_mode,
                codegen_llm=codegen_llm,
                reader_llm=local_llm,
                shell_llm=local_llm,
                direct_llm=local_llm,
            )
            if ai_reply:
                memory.append_activity(cfg["workspace"], user_input, ai_reply)
                memory.update_context(cfg["workspace"], user_input)
            continue

        if cmd.startswith("/brainstorm"):
            _set_current_task("Brainstorming")
            _print_progress_message(
                "Running explicit brainstorm mode",
                "This turn will be saved to `.codemitra/brainstorm.md`.",
            )
            ai_reply = _cmd_brainstorm(user_input, cfg["workspace"], local_llm)
            console.print(Panel(Markdown(ai_reply), title="[bold cyan]CodeMitra[/bold cyan]", border_style="cyan"))
            memory.append_activity(cfg["workspace"], user_input, ai_reply)
            memory.update_context(cfg["workspace"], user_input)
            continue

        if cmd == "/memory":
            _cmd_memory(cfg["workspace"])
            continue

        if cmd.startswith("/skills"):
            ai_reply = _build_skills_reply(available_skills, user_input, workspace=cfg["workspace"])
            console.print(Panel(Markdown(ai_reply), title="[bold cyan]CodeMitra[/bold cyan]", border_style="cyan"))
            memory.append_activity(cfg["workspace"], user_input, ai_reply)
            memory.update_context(cfg["workspace"], user_input)
            continue

        if cmd == "/context":
            ai_reply = _build_context_reply(sess_in + sess_out, auto_compact_threshold, num_ctx)
            console.print(Panel(Markdown(ai_reply), title="[bold cyan]CodeMitra[/bold cyan]", border_style="cyan"))
            memory.append_activity(cfg["workspace"], user_input, ai_reply)
            memory.update_context(cfg["workspace"], user_input)
            continue

        if cmd == "/status":
            ai_reply = _build_status_reply(
                cfg["workspace"],
                model,
                codegen_model,
                cloud_codegen_enabled=bool(cloud_api_key),
                session_mode=session_mode,
                show_reasoning=show_reasoning,
                total_tokens=sess_in + sess_out,
                auto_compact_threshold=auto_compact_threshold,
                num_ctx=num_ctx,
            )
            console.print(Panel(Markdown(ai_reply), title="[bold cyan]CodeMitra[/bold cyan]", border_style="cyan"))
            memory.append_activity(cfg["workspace"], user_input, ai_reply)
            memory.update_context(cfg["workspace"], user_input)
            continue

        if cmd == "/permissions":
            ai_reply = _build_permissions_reply(cfg, session_mode)
            console.print(Panel(Markdown(ai_reply), title="[bold cyan]CodeMitra[/bold cyan]", border_style="cyan"))
            memory.append_activity(cfg["workspace"], user_input, ai_reply)
            memory.update_context(cfg["workspace"], user_input)
            continue

        if cmd.startswith("/mode"):
            requested = user_input.strip()[5:].strip()
            if not requested:
                ai_reply = _build_mode_reply(session_mode)
            else:
                normalized = _normalize_session_mode(requested)
                if normalized != requested.strip().lower():
                    ai_reply = f"Unknown mode: `{requested}`. Available modes: `read-only`, `plan`, `approve`, `auto`."
                else:
                    session_mode = normalized
                    _apply_session_mode(cfg, session_mode)
                    prompt_str = _build_prompt_label(model, session_mode)
                    ai_reply = _build_mode_reply(session_mode)
            console.print(Panel(Markdown(ai_reply), title="[bold cyan]CodeMitra[/bold cyan]", border_style="cyan"))
            memory.append_activity(cfg["workspace"], user_input, ai_reply)
            memory.update_context(cfg["workspace"], user_input)
            continue

        if cmd.startswith("/thinking"):
            requested = user_input.strip()[9:].strip().lower()
            if not requested:
                ai_reply = _build_reasoning_reply(show_reasoning)
            elif requested in {"on", "show", "true"}:
                show_reasoning = True
                ai_reply = _build_reasoning_reply(show_reasoning)
            elif requested in {"off", "hide", "false"}:
                show_reasoning = False
                ai_reply = _build_reasoning_reply(show_reasoning)
            else:
                ai_reply = "Usage: `/thinking on` or `/thinking off`."
            console.print(Panel(Markdown(ai_reply), title="[bold cyan]CodeMitra[/bold cyan]", border_style="cyan"))
            memory.append_activity(cfg["workspace"], user_input, ai_reply)
            memory.update_context(cfg["workspace"], user_input)
            continue

        if cmd.startswith("/model"):
            ai_reply = _handle_model_command(
                user_input,
                model,
                codegen_model,
                cloud_codegen_enabled=bool(cloud_api_key),
            )
            console.print(Panel(Markdown(ai_reply), title="[bold cyan]CodeMitra[/bold cyan]", border_style="cyan"))
            memory.append_activity(cfg["workspace"], user_input, ai_reply)
            memory.update_context(cfg["workspace"], user_input)
            continue

        if cmd == "/history":
            ai_reply = _build_history_reply(cfg["workspace"])
            console.print(Panel(Markdown(ai_reply), title="[bold cyan]CodeMitra[/bold cyan]", border_style="cyan"))
            memory.append_activity(cfg["workspace"], user_input, ai_reply)
            memory.update_context(cfg["workspace"], user_input)
            continue

        if cmd == "/resume":
            _set_current_task("Resuming session")
            _print_progress_message("Resuming the current session", "Loading the saved session summary, plan, and recent activity.")
            ai_reply = _cmd_resume(cfg["workspace"])
            memory.append_activity(cfg["workspace"], user_input, ai_reply)
            memory.update_context(cfg["workspace"], user_input)
            continue

        if cmd.startswith("/rename"):
            ai_reply = _cmd_rename(user_input, cfg["workspace"])
            console.print(Panel(Markdown(ai_reply), title="[bold cyan]CodeMitra[/bold cyan]", border_style="cyan"))
            memory.append_activity(cfg["workspace"], user_input, ai_reply)
            memory.update_context(cfg["workspace"], user_input)
            continue

        if cmd == "/diff":
            ai_reply = _build_diff_reply(cfg["workspace"])
            console.print(Panel(Markdown(ai_reply), title="[bold cyan]CodeMitra[/bold cyan]", border_style="cyan"))
            memory.append_activity(cfg["workspace"], user_input, ai_reply)
            memory.update_context(cfg["workspace"], user_input)
            continue

        if cmd.startswith("/review"):
            review_target = _parse_review_target(user_input)
            detail = "Checking the staged git diff and status." if review_target == "staged" else "Checking the current git diff or last CodeMitra change set."
            _print_progress_message("Reviewing current changes", detail)
            ai_reply = _cmd_review(cfg["workspace"], local_llm, target=review_target)
            memory.append_activity(cfg["workspace"], user_input, ai_reply)
            memory.update_context(cfg["workspace"], user_input)
            continue

        if cmd.startswith("/explain"):
            _print_progress_message("Explaining the requested file", "Reading the file and summarizing how it works.", color="magenta")
            ai_reply = _cmd_explain(user_input, cfg["workspace"], local_llm)
            memory.append_activity(cfg["workspace"], user_input, ai_reply)
            memory.update_context(cfg["workspace"], user_input)
            continue

        if cmd.startswith("/symbols"):
            _print_progress_message("Looking up symbol intelligence", "Finding definitions and usages across the workspace.", color="cyan")
            ai_reply = _cmd_symbols(user_input, cfg["workspace"])
            memory.append_activity(cfg["workspace"], user_input, ai_reply)
            memory.update_context(cfg["workspace"], user_input)
            continue

        if cmd.startswith("/search"):
            _print_progress_message("Searching the web", user_input.strip()[7:].strip()[:120], color="cyan")
            ai_reply = _cmd_search(user_input, local_llm)
            memory.append_activity(cfg["workspace"], user_input, ai_reply)
            memory.update_context(cfg["workspace"], user_input)
            continue

        if cmd.startswith("/open-url"):
            _print_progress_message("Reading the webpage", user_input.strip()[9:].strip()[:120], color="cyan")
            ai_reply = _cmd_open_url(user_input, local_llm)
            memory.append_activity(cfg["workspace"], user_input, ai_reply)
            memory.update_context(cfg["workspace"], user_input)
            continue

        if cmd == "/undo":
            ai_reply = filesystem.undo_last_change_set(cfg["workspace"])
            console.print(Panel(Markdown(ai_reply), title="[bold cyan]CodeMitra[/bold cyan]", border_style="cyan"))
            memory.append_activity(cfg["workspace"], user_input, ai_reply)
            memory.update_context(cfg["workspace"], user_input)
            continue

        if cmd.startswith("/tasks"):
            ai_reply = _build_tasks_reply(user_input)
            console.print(Panel(Markdown(ai_reply), title="[bold cyan]CodeMitra[/bold cyan]", border_style="cyan"))
            memory.append_activity(cfg["workspace"], user_input, ai_reply)
            memory.update_context(cfg["workspace"], user_input)
            continue

        if cmd.startswith("/fix"):
            fix_command = _extract_fix_command(user_input, last_command=_LAST_SHELL_COMMAND)
            ai_reply = _cmd_fix(fix_command or "", cfg["workspace"], codegen_llm)
            console.print(Panel(Markdown(ai_reply), title="[bold cyan]CodeMitra[/bold cyan]", border_style="cyan"))
            memory.append_activity(cfg["workspace"], user_input, ai_reply)
            memory.update_context(cfg["workspace"], user_input)
            continue

        if cmd == "/compact":
            messages = _compact(
                local_llm,
                messages,
                system_prompt,
                workspace=cfg["workspace"],
                reason="manual",
                total_tokens=sess_in + sess_out,
            )
            sess_in = sess_out = 0
            continue

        if cmd == "/hibernate":
            _set_current_task("Hibernating session")
            _print_progress_message(
                "Saving workspace state and unloading the model",
                "CodeMitra is persisting session memory, resetting chat history, and asking Ollama to release RAM.",
                color="yellow",
            )
            messages, sess_in, sess_out, ai_reply = _hibernate_session(
                workspace=cfg["workspace"],
                model=model,
                system_prompt=system_prompt,
                total_tokens=sess_in + sess_out,
                auto_compact_threshold=auto_compact_threshold,
            )
            console.print(Panel(Markdown(ai_reply), title="[bold cyan]CodeMitra[/bold cyan]", border_style="cyan"))
            continue

        if cmd.startswith("/run "):
            raw_cmd, run_in_background = _parse_run_command(user_input)
            if run_in_background:
                _set_current_task("Starting background task")
                ai_reply = _cmd_run_background(raw_cmd, cfg["workspace"])
                console.print(Panel(Markdown(ai_reply), title="[bold cyan]CodeMitra[/bold cyan]", border_style="cyan"))
                memory.append_activity(cfg["workspace"], user_input, ai_reply)
                memory.update_context(cfg["workspace"], user_input)
            else:
                _cmd_run(raw_cmd)
            continue

        if intent == "run" and _looks_like_explicit_command(user_input):
            _cmd_run(_extract_command(user_input))
            continue

        messages.append(HumanMessage(content=user_input))

        # ── Turn separator ────────────────────────────────────────────────────
        console.print()
        console.print(Rule(style="dim"))

        try:
            # ── Invoke with streaming ─────────────────────────────────────────
            turn_in = turn_out = 0

            # Stream tokens for direct replies; invoke() for tool-call routing.
            # Strategy: stream first, collect; if tool_calls in final chunk switch mode.
            streamed_chunks: list = []
            streamed_text = ""
            has_tool_calls = False

            _print_progress_message("Thinking through the request")
            with console.status("[bold green]Thinking...[/bold green]", spinner="dots") as status:
                for chunk in main_llm.stream(messages):
                    streamed_chunks.append(chunk)
                    if getattr(chunk, "tool_call_chunks", None):
                        has_tool_calls = True
                    content_piece = getattr(chunk, "content", "") or ""
                    if isinstance(content_piece, str):
                        streamed_text += content_piece

            # Reconstruct AIMessage from streamed chunks
            response = streamed_chunks[-1]
            for c in streamed_chunks[:-1]:
                try:
                    response = c + response
                except Exception:
                    pass

            # Fall back to invoke if streaming didn't give tool calls properly
            if not response.tool_calls and has_tool_calls:
                with console.status("[bold green]Thinking...[/bold green]"):
                    response = main_llm.invoke(messages)

            t_in, t_out = _get_tokens(response)
            turn_in += t_in; turn_out += t_out
            messages.append(response)

            # ── Show thinking (models that emit <think>…</think>) ─────────────
            thinking, clean_content = _extract_thinking(response.content or "")
            if thinking and show_reasoning:
                console.print(
                    Panel(
                        f"[dim italic]{thinking[:3000]}{'…' if len(thinking) > 3000 else ''}[/dim italic]",
                        title="[dim]Thinking[/dim]",
                        border_style="dim",
                        padding=(0, 1),
                    )
                )

            ai_reply = ""
            skip_follow_up = False

            if response.tool_calls:
                for tc in response.tool_calls:
                    request = tc["args"].get("request", user_input)

                    if tc["name"] == "run_command":
                        # ── Shell Agent ───────────────────────────────────────
                        _print_progress_message("Running shell command", request[:120], color="blue")
                        _LAST_SHELL_COMMAND = _extract_command(request)
                        shell_result = shell_agent.execute(
                            command=_LAST_SHELL_COMMAND,
                            cwd=None,
                            console=console,
                        )
                        console.print(shell_agent.render(shell_result))
                        messages.append(ToolMessage(content=shell_result.to_llm_summary(), tool_call_id=tc["id"]))
                        ai_reply = shell_result.to_llm_summary()
                    elif tc["name"] == "read_codebase":
                        # ── Code Reader Agent ─────────────────────────────────
                        _print_progress_message("Inspecting the codebase", request[:120], color="magenta")
                        reader_resp = reader_agent.run(local_llm, request, console=console)
                        turn_in  += reader_resp.tokens_in
                        turn_out += reader_resp.tokens_out
                        messages.append(ToolMessage(content=reader_resp.summary, tool_call_id=tc["id"]))
                        console.print(reader_agent.render(reader_resp))
                        ai_reply = reader_resp.summary
                        skip_follow_up = True
                    elif tc["name"] == "browse_web":
                        _print_progress_message("Searching the web", request[:120], color="cyan")
                        web_resp = web_agent.run(local_llm, request, console=console)
                        turn_in += web_resp.tokens_in
                        turn_out += web_resp.tokens_out
                        messages.append(ToolMessage(content=web_resp.summary, tool_call_id=tc["id"]))
                        console.print(web_agent.render(web_resp))
                        ai_reply = web_resp.summary
                        skip_follow_up = True
                    elif tc["name"] == "execute_plan":
                        # ── Planner Agent ─────────────────────────────────────
                        _print_progress_message("Executing the active plan", request[:120], color="yellow")
                        plan_summary = _execute_approved_plan(
                            workspace=cfg["workspace"],
                            llm=local_llm,
                            max_steps=1,
                            session_mode=session_mode,
                            codegen_llm=codegen_llm,
                            reader_llm=local_llm,
                            shell_llm=local_llm,
                            direct_llm=local_llm,
                        )
                        messages.append(ToolMessage(content=plan_summary, tool_call_id=tc["id"]))
                        ai_reply = plan_summary
                    else:
                        # ── Filesystem Agent ──────────────────────────────────
                        _print_progress_message("Applying file changes", request[:120])
                        agent_resp = filesystem.run(codegen_llm, request, console=console)
                        turn_in += agent_resp.tokens_in
                        turn_out += agent_resp.tokens_out
                        messages.append(ToolMessage(content=agent_resp.summary, tool_call_id=tc["id"]))
                        console.print(render(agent_resp))
                        ai_reply = agent_resp.summary

                if not skip_follow_up:
                    _print_progress_message("Summarizing the result")
                    with console.status("[bold green]Summarizing the result...[/bold green]", spinner="dots"):
                        follow_up = main_llm.invoke(messages)
                    f_in, f_out = _get_tokens(follow_up)
                    turn_in += f_in; turn_out += f_out
                    messages.append(follow_up)
                    _, fu_content = _extract_thinking(follow_up.content or "")
                    if fu_content.strip():
                        console.print(
                            Panel(
                                Markdown(fu_content),
                                title="[bold cyan]CodeMitra[/bold cyan]",
                                border_style="cyan",
                            )
                        )
                        ai_reply = fu_content.strip()

            elif clean_content.strip():
                ai_reply = clean_content.strip()
                # Render markdown (syntax highlighting for code fences)
                console.print(
                    Panel(
                        Markdown(ai_reply),
                        title="[bold cyan]CodeMitra[/bold cyan]",
                        border_style="cyan",
                    )
                )

            # ── Token bar ─────────────────────────────────────────────────────
            sess_in += turn_in; sess_out += turn_out
            if turn_in or turn_out:
                total = sess_in + sess_out
                pct = min(100, int(total / auto_compact_threshold * 100))
                bar_filled = pct // 5   # 20 chars wide
                bar = "█" * bar_filled + "░" * (20 - bar_filled)
                compact_hint = "  [yellow bold]⚡ /compact[/yellow bold]" if total >= auto_compact_threshold * 0.8 else ""
                console.print(
                    f"  [dim]tokens  ↑ {turn_in:,} in  ↓ {turn_out:,} out"
                    f"  ·  session {total:,} [{bar}] {pct}%[/dim]{compact_hint}"
                )

            # ── Auto-compact ──────────────────────────────────────────────────
            if sess_in + sess_out >= auto_compact_threshold:
                console.print(
                    "\n[yellow]⚡ Context window is full. Auto-compacting history...[/yellow]"
                )
                messages = _compact(
                    local_llm,
                    messages,
                    system_prompt,
                    workspace=cfg["workspace"],
                    reason="auto",
                    total_tokens=sess_in + sess_out,
                )
                sess_in = sess_out = 0

            # ── Persist to memory ─────────────────────────────────────────
            if ai_reply:
                memory.append_activity(cfg["workspace"], user_input, ai_reply)
                memory.update_context(cfg["workspace"], user_input)

        except KeyboardInterrupt:
            _set_current_task("Ready")
            console.print("\n[dim]Interrupted.[/dim]")
        except Exception as e:
            _set_current_task("Ready")
            _log_error(cfg["workspace"], e)
            console.print(
                Panel(
                    f"[red]⚠  {_friendly_error(e)}[/red]\n"
                    f"[dim](Full trace saved to .codemitra/errors.log)[/dim]",
                    title="[bold red]Error[/bold red]",
                    border_style="red",
                )
            )


def _cmd_plan(
    raw: str,
    workspace: str,
    llm=None,
    *,
    session_mode: str = "approve",
    codegen_llm=None,
    reader_llm=None,
    shell_llm=None,
    direct_llm=None,
) -> str | None:
    """Handle `/plan <goal>` — brainstorm clarifying questions, then generate AI steps."""
    goal = raw.strip()[5:].strip()  # strip "/plan "
    if not goal:
        existing = memory.load_plan(workspace)
        if existing:
            plan = planner_agent._parse_plan(workspace)
            if plan:
                console.print(planner_agent.render(plan))
            else:
                console.print(Panel(existing, title="[bold cyan]Active Plan[/bold cyan]", border_style="cyan"))
        else:
            console.print("[dim]No active plan. Use [cyan]/plan <your goal>[/cyan] to create one.[/dim]")
        return None

    subcommand = goal.lower()
    if subcommand in {"approve", "pause", "next", "run"}:
        if subcommand == "approve":
            reply = planner_agent.approve_plan(workspace)
        elif subcommand == "pause":
            reply = planner_agent.pause_plan(workspace)
        else:
            _print_progress_message(
                "Executing the active plan",
                "Running one approved step." if subcommand == "next" else "Running approved pending steps.",
                color="yellow",
            )
            reply = _execute_approved_plan(
                workspace=workspace,
                llm=llm,
                max_steps=1 if subcommand == "next" else None,
                session_mode=session_mode,
                codegen_llm=codegen_llm,
                reader_llm=reader_llm,
                shell_llm=shell_llm,
                direct_llm=direct_llm,
            )
        console.print(Panel(Markdown(reply), title="[bold cyan]CodeMitra[/bold cyan]", border_style="cyan"))
        return reply

    if llm is not None:
        from app.agents import brainstorm as brainstorm_agent
        context = brainstorm_agent.run(llm, goal, console)
        with console.status("[bold green]Generating plan...[/bold green]"):
            plan = planner_agent.create_plan(llm, goal, workspace, context=context)
        console.print(f"[dim cyan]  ✦  Plan written to .codemitra/plan.md[/dim cyan]")
        console.print(planner_agent.render(plan))
        console.print("[dim]Use [cyan]/plan approve[/cyan] when you're ready, then [cyan]/plan next[/cyan].[/dim]")
        return f"Created a plan for: {goal}"
    else:
        # Fallback: write a generic plan without AI step generation
        path = memory.write_plan(workspace, goal=goal, steps=[
            "Understand current codebase structure",
            "Break goal into sub-tasks",
            "Implement each sub-task step by step",
            "Test and verify",
        ])
        planner_agent._reset_plan_execution_state(workspace, goal)
        console.print(f"[dim cyan]  ✦  Plan written to {path.relative_to(pathlib.Path(workspace))}[/dim cyan]")
        plan = planner_agent._parse_plan(workspace)
        if plan:
            console.print(planner_agent.render(plan))
        return f"Created a plan for: {goal}"


def _cmd_memory(workspace: str) -> None:
    """Handle `/memory` — show saved CodeMitra workspace artifacts."""
    ctx = memory.load_context(workspace)
    plan = memory.load_plan(workspace)
    brainstorm = memory.load_brainstorm(workspace)
    if not ctx and not plan and not brainstorm:
        console.print("[dim]No memory yet. Start chatting and it will build automatically.[/dim]")
        return
    if ctx:
        console.print(Panel(ctx, title="[bold cyan].codemitra/context.md[/bold cyan]", border_style="cyan"))
    if plan:
        console.print(Panel(plan, title="[bold cyan].codemitra/plan.md[/bold cyan]", border_style="cyan"))
    if brainstorm:
        console.print(Panel(brainstorm, title="[bold cyan].codemitra/brainstorm.md[/bold cyan]", border_style="cyan"))


def _cmd_brainstorm(raw: str, workspace: str, llm) -> str:
    topic = raw.strip()[11:].strip()
    if not topic:
        existing = memory.load_brainstorm(workspace)
        return existing or "No brainstorm notes yet. Use `/brainstorm <topic>` to start saving idea exploration."

    reply = _run_brainstorm_reply(llm, workspace, topic)
    return _save_brainstorm_reply(workspace, topic, reply)


def _amend_command(original: str) -> str | None:
    """Let the user edit the command inline before running it.

    Pre-fills the prompt with the original command so the user can adjust it.
    Returns the edited command, or None if the user cancels (Ctrl+C / empty submit).
    """
    from prompt_toolkit import prompt as pt_prompt
    from prompt_toolkit.history import InMemoryHistory

    console.print(
        "\n  [bold yellow]Amend command[/bold yellow] — edit below, then press Enter to run. Ctrl+C to cancel.\n"
    )
    history = InMemoryHistory()
    history.append_string(original)
    try:
        amended = pt_prompt("  $ ", default=original, history=history).strip()
    except (KeyboardInterrupt, EOFError):
        _print_approval_result("Cancelled", approved=False)
        return None
    if not amended:
        _print_approval_result("Cancelled (empty command)", approved=False)
        return None
    if amended != original:
        _print_approval_result(f"Amended to: {amended}", approved=True)
    else:
        _print_approval_result("Approved (unchanged)", approved=True)
    return amended


def _confirm_shell(command: str, cwd: str) -> str | None:
    """Ask the user before the shell agent runs any command.

    Returns the (possibly amended) command string to run, or None to deny.
    """
    workspace = shell_agent._config.root_workspace or cwd
    command_name = _shell_command_name(command)
    if memory.is_shell_command_trusted(workspace, cwd, command_name):
        _print_approval_result(f"Trusted `{command_name}` in {cwd}", approved=True)
        return command

    choice = _choose_approval_option(
        "Run shell command",
        f"Command:\n{command}\n\nDirectory:\n{cwd}\n\nChoose how to handle this command.",
        [
            ("approve", "Yes"),
            ("trust", f"Yes, and don't ask again for `{command_name}` in this directory"),
            ("amend", "Tab to amend — edit the command before running"),
            ("deny", "No, and cancel this command"),
        ],
        fallback_default="approve",
    )
    if choice == "trust":
        memory.trust_shell_command(workspace, cwd, command_name)
        _print_approval_result(f"Approved and trusted `{command_name}` in {cwd}", approved=True)
        return command
    if choice == "amend":
        return _amend_command(command)
    approved = choice == "approve"
    _print_approval_result("Approved" if approved else "Skipped", approved=approved)
    return command if approved else None


def _cmd_run(command: str, workspace: str | None = None) -> None:
    """/run <command> — execute a command directly in the workspace."""
    if not command:
        console.print("[dim]Usage: [cyan]/run <command>[/cyan]  e.g. /run python main.py[/dim]")
        return
    global _LAST_SHELL_COMMAND
    _LAST_SHELL_COMMAND = command
    _print_progress_message("Running shell command", command, color="blue")
    result = shell_agent.execute(command=command, cwd=workspace, console=console)
    console.print(shell_agent.render(result))


def _parse_run_command(raw: str) -> tuple[str, bool]:
    command = raw.strip()
    if command.startswith("/run"):
        command = command[4:].strip()
    lowered = command.lower()
    for prefix in ("--background ", "-b ", "bg "):
        if lowered.startswith(prefix):
            return command[len(prefix):].strip(), True
    return command, False


def _cmd_run_background(command: str, workspace: str | None = None) -> str:
    """Launch a shell command in the background and return a task summary."""
    if not command:
        return "Usage: `/run --background <command>`"

    global _LAST_SHELL_COMMAND
    _LAST_SHELL_COMMAND = command
    task, error = shell_agent.start_background(command=command, cwd=workspace)
    if error:
        return error
    if task is None:
        return "Could not start the background task."
    return (
        "## Background task started\n\n"
        f"- **Task:** `{task.id}`\n"
        f"- **Command:** `{task.command}`\n"
        f"- **Directory:** `{task.cwd}`\n"
        f"- **Status:** `{task.status}`\n\n"
        "Use `/tasks` to inspect it, `/tasks show <id>` for output, or `/tasks stop <id>` to stop it."
    )


def _build_tasks_reply(raw: str) -> str:
    target = raw.strip()[6:].strip() if raw.strip().startswith("/tasks") else raw.strip()
    if not target:
        tasks = shell_agent.list_background_tasks()
        if not tasks:
            return "No background tasks yet. Use `/run --background <command>` to start one."
        running = sum(1 for task in tasks if task.status == "running")
        lines = [
            "## Background tasks",
            "",
            f"- **Running:** `{running}`",
            f"- **Tracked total:** `{len(tasks)}`",
            "",
        ]
        for task in reversed(tasks[-8:]):
            status = task.status
            lines.append(f"- **{task.id}** · `{status}` · `{task.command}`")
            lines.append(f"  - **CWD:** `{task.cwd}`")
            if task.exit_code is not None:
                lines.append(f"  - **Exit:** `{task.exit_code}`")
        lines.extend([
            "",
            "Use `/tasks show <id>` for details or `/tasks stop <id>` to stop a running task.",
        ])
        return "\n".join(lines)

    if target.startswith("show "):
        task_id = target[5:].strip()
        task = shell_agent.get_background_task(task_id)
        if task is None:
            return f"No background task found for `{task_id}`."
        lines = [
            "## Background task",
            "",
            f"- **Task:** `{task.id}`",
            f"- **Command:** `{task.command}`",
            f"- **Directory:** `{task.cwd}`",
            f"- **Status:** `{task.status}`",
            f"- **Started:** `{task.started_at}`",
        ]
        if task.completed_at:
            lines.append(f"- **Completed:** `{task.completed_at}`")
        if task.exit_code is not None:
            lines.append(f"- **Exit:** `{task.exit_code}`")
        if task.note:
            lines.append(f"- **Note:** {task.note}")
        lines.extend(["", "```text", task.tail or "(no output yet)", "```"])
        return "\n".join(lines)

    if target.startswith("stop "):
        task_id = target[5:].strip()
        existing = shell_agent.get_background_task(task_id)
        if existing is None:
            return f"No background task found for `{task_id}`."
        if existing.status != "running":
            return f"Background task `{task_id}` is already `{existing.status}`."
        task, error = shell_agent.stop_background_task(task_id)
        if error:
            return error
        if task is None:
            return f"No background task found for `{task_id}`."
        return (
            "## Background task stopped\n\n"
            f"- **Task:** `{task.id}`\n"
            f"- **Command:** `{task.command}`\n"
            f"- **Status:** `{task.status}`"
        )

    return "Usage: `/tasks`, `/tasks show <id>`, or `/tasks stop <id>`."


def _extract_fix_command(raw: str, *, last_command: str | None = None) -> str | None:
    target = raw.strip()[4:].strip()
    if not target:
        return last_command
    if target.lower().startswith("/run "):
        return target[5:].strip() or last_command
    return _extract_command(target).strip() or last_command


def _build_fix_usage(last_command: str | None = None) -> str:
    example = last_command or "pytest"
    return (
        "Usage: `/fix <failing command>`\n\n"
        f"Example: `/fix {example}`\n\n"
        "If you already ran a command in this session, `/fix` without arguments will reuse it."
    )


def _build_fix_prompt(command: str, result: shell_agent.ShellResult, attempt: int, max_attempts: int) -> str:
    tail = result.tail or result.output or "(no output)"
    return (
        f"The command `{command}` failed in the current workspace.\n\n"
        f"This is repair attempt {attempt} of {max_attempts}.\n"
        "Inspect the relevant files, apply the smallest safe code changes needed, and stop after the edits.\n"
        "Do not run shell commands yourself; I will rerun the failing command after your patch.\n"
        "Prefer fixing the actual failure over broad refactors.\n\n"
        "Failure details:\n"
        f"{tail}"
    )


def _response_has_code_changes(agent_response) -> bool:
    mutating_tools = {"create_file", "move_file", "delete_file", "delete_folder", "create_folder"}
    return any(step.tool in mutating_tools and step.ok for step in agent_response.steps)


def _cmd_fix(command: str, workspace: str, codegen_llm) -> str:
    global _LAST_SHELL_COMMAND
    if not command:
        return _build_fix_usage(_LAST_SHELL_COMMAND)

    attempt = 0
    last_result = None

    while attempt < _FIX_MAX_ATTEMPTS:
        attempt += 1
        _LAST_SHELL_COMMAND = command

        _print_progress_message(
            f"Repair attempt {attempt}/{_FIX_MAX_ATTEMPTS}",
            f"Running `{command}` to confirm the current failure.",
            color="yellow",
        )

        shell_result = shell_agent.execute(command=command, cwd=None, console=console)
        console.print(shell_agent.render(shell_result))
        last_result = shell_result

        if shell_result.denied:
            return "Repair stopped because the failing command was not approved."
        if shell_result.ok:
            if attempt == 1:
                return f"The command `{command}` is already passing."
            return f"Fixed after {attempt - 1} repair attempt{'s' if attempt - 1 != 1 else ''}. `{command}` now passes."
        if attempt >= _FIX_MAX_ATTEMPTS:
            break

        repair_request = _build_fix_prompt(command, shell_result, attempt, _FIX_MAX_ATTEMPTS)
        _print_progress_message("Applying a targeted patch", f"Repair attempt {attempt} is editing the code now.")
        agent_resp = filesystem.run(codegen_llm, repair_request, console=console)
        console.print(render(agent_resp))

        if not _response_has_code_changes(agent_resp):
            return (
                f"Repair stopped after attempt {attempt} because no code changes were applied.\n\n"
                f"Latest command output:\n{shell_result.tail or shell_result.output or '(no output)'}"
            )

    latest = last_result.tail if last_result else "(no output)"
    return (
        f"Repair stopped after {_FIX_MAX_ATTEMPTS} attempts. `{command}` is still failing.\n\n"
        f"Latest command output:\n{latest}"
    )


def _extract_command(request: str) -> str:
    """Pull a bare shell command out of a natural-language request.

    Looks for backtick-quoted text first, then takes the whole request as-is
    so the shell agent's LLM loop can handle it directly.
    """
    import re
    match = re.search(r"`([^`]+)`", request)
    return match.group(1) if match else request


def _confirm_tool(tool_name: str, args: dict) -> bool:
    """Ask the user before the filesystem agent executes a guarded file operation."""
    _LABELS = {
        "delete_file":   ("Delete file",   "red"),
        "delete_folder": ("Delete folder", "red"),
        "move_file":     ("Move / rename", "yellow"),
        "create_file":   ("Overwrite file", "yellow"),
    }
    label, _colour = _LABELS.get(tool_name, (tool_name, "yellow"))

    if tool_name == "move_file":
        detail = f"{args.get('src', '?')}  →  {args.get('dest', '?')}"
    else:
        detail = args.get("path", "?")

    preview = ""
    if tool_name == "create_file":
        preview = _build_diff_preview(detail, args.get("content", ""))
        title = "File diff preview"
    elif tool_name == "move_file":
        preview = _build_move_preview(args.get("src", ""), args.get("dest", ""))
        title = "Destructive operation"
    else:
        title = "Destructive operation"

    choice = _choose_approval_option(
        title,
        f"Action: {label}\nTarget: {detail}\n\n{preview or 'No preview available.'}\n\nChoose what to do next.",
        [
            ("deny", f"No, skip {label.lower()}"),
            ("approve", f"Yes, approve {label.lower()}"),
        ],
        fallback_default="deny",
    )
    approved = choice == "approve"
    _print_approval_result("Approved" if approved else "Skipped", approved=approved)
    return approved


def _build_diff_preview(path: str, new_content: str, max_lines: int = 60) -> str:
    """Return a small unified diff preview for an existing file overwrite."""
    target = pathlib.Path(path)
    try:
        old_content = target.read_text(encoding="utf-8")
    except Exception as exc:
        return f"(Could not read current file for diff preview: {exc})"

    if old_content == new_content:
        return "(No content changes)"

    diff_lines = list(
        difflib.unified_diff(
            old_content.splitlines(),
            new_content.splitlines(),
            fromfile=f"current\\{target.name}",
            tofile=f"new\\{target.name}",
            lineterm="",
        )
    )
    if len(diff_lines) > max_lines:
        hidden = len(diff_lines) - max_lines
        diff_lines = diff_lines[:max_lines] + [f"... ({hidden} more lines omitted)"]
    return "\n".join(diff_lines)


def _build_move_preview(src: str, dest: str) -> str:
    try:
        source = filesystem._resolve_path(src)
        destination = filesystem._resolve_path(dest)
    except Exception:
        return "Move the selected file or folder. Imports and package names stay unchanged unless you ask for that too."

    if not source.exists():
        return (
            "Source path: not found inside the current workspace\n"
            "Destination: "
            + ("already exists" if destination.exists() else "will be created as the new path")
            + "\nNote: if you meant the current project root folder itself, rename it from the parent directory instead of inside this workspace."
        )

    source_type = "folder" if source.is_dir() else "file"
    destination_state = "already exists" if destination.exists() else "will be created as the new path"
    lines = [
        f"Source type: {source_type}",
        f"Destination: {destination_state}",
        "Note: this only renames/moves the selected path. Imports and package names stay unchanged unless you request that too. Internal code references also stay unchanged by default.",
    ]
    return "\n".join(lines)


def _parse_rename_request(user_input: str) -> tuple[str, str] | None:
    normalized = re.sub(r"\s+", " ", user_input.strip().lower())
    patterns = [
        r"rename (?:the )?(?:folder |directory |project )?from ([\w\-. ]+) to ([\w\-. ]+)",
        r"change (?:the )?([\w\-. ]+) name to ([\w\-. ]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, normalized)
        if match:
            src = match.group(1).strip(" .")
            dest = match.group(2).strip(" .")
            if src and dest:
                return src, dest
    return None


def _build_root_rename_reply(user_input: str, workspace: str) -> str | None:
    parsed = _parse_rename_request(user_input)
    if not parsed:
        return None

    src, dest = parsed
    root = pathlib.Path(workspace)
    workspace_name = root.name.lower()
    if src != workspace_name:
        return None

    parent = root.parent
    destination_path = parent / dest
    extra = ""
    if (root / dest).exists():
        extra = (
            f"\n\nAlso, `{dest}` already exists inside the current workspace, so a nested rename is not what you want here."
        )

    return (
        f"The current project root is already `{root.name}`, and CodeMitra is locked inside that workspace, so it cannot rename the root folder from within itself.{extra}\n\n"
        "If you want to rename the project folder, run this from the parent folder in PowerShell:\n\n"
        f"1. `Set-Location '{parent}'`\n"
        f"2. `Rename-Item '{root.name}' '{dest}'`\n\n"
        f"That would rename:\n`{root}`\n→ `{destination_path}`"
    )


def _build_root_delete_reply(workspace: str) -> str:
    root = pathlib.Path(workspace)
    parent = root.parent
    return (
        f"CodeMitra is locked inside `{root.name}`, so it cannot delete the current project root from within itself.\n\n"
        "If you want to remove the whole project and start fresh, run this from the parent folder in PowerShell:\n\n"
        f"1. `Set-Location '{parent}'`\n"
        f"2. `Remove-Item '{root.name}' -Recurse -Force`\n\n"
        f"That would delete:\n`{root}`"
    )


# ── Tokens at which auto-compact kicks in ────────────────────────────────────
_AUTO_COMPACT_THRESHOLD = 120_000  # overridden at runtime from codemitra.toml


def _compact(
    llm,
    messages: list,
    system_prompt: str,
    *,
    workspace: str | None = None,
    reason: str = "manual",
    total_tokens: int | None = None,
) -> list:
    """
    Summarise the conversation so far and return a fresh messages list.
    The system prompt is kept; everything else is replaced with a single
    HumanMessage containing the condensed history.
    """
    from langchain_core.messages import HumanMessage as HM

    # Only summarise if there is history beyond the system prompt
    history = [m for m in messages if not isinstance(m, SystemMessage)]
    if not history:
        console.print("[dim]Nothing to compact.[/dim]")
        return messages

    turns_text = []
    for m in history:
        role = type(m).__name__.replace("Message", "")
        turns_text.append(f"{role}: {getattr(m, 'content', '') or ''}")
    history_blob = "\n".join(turns_text)

    summarise_prompt = (
        "Summarise the following conversation history concisely. "
        "Keep all key decisions, file names, code snippets, errors, and next steps. "
        "Output plain text — no JSON, no tool calls.\n\n"
        + history_blob
    )

    with console.status("[bold green]Compacting history...[/bold green]"):
        summary_msg = llm.invoke([HM(content=summarise_prompt)])

    summary = (summary_msg.content or "").strip()
    if workspace:
        session_meta = session_agent.ensure_session(workspace)
        compact_meta = {
            "reason": reason,
            "summary": summary,
            "compacted_at": datetime.now().isoformat(timespec="seconds"),
            "turns_compacted": len(history),
        }
        if total_tokens is not None:
            compact_meta["usage_tokens_before"] = total_tokens
        memory.save_session_metadata(
            workspace,
            {
                **session_meta,
                "last_compaction": compact_meta,
            },
        )
    console.print(
        Panel(
            summary,
            title="[bold yellow]Compacted History[/bold yellow]",
            border_style="yellow",
        )
    )
    console.print("[dim]Context window cleared — summary injected as new context.[/dim]")
    return [
        SystemMessage(content=system_prompt),
        HM(content=f"[Compacted context from previous turns]\n\n{summary}"),
    ]


def _print_help():
    table = Table.grid(padding=(0, 2))
    table.add_column(style="cyan", no_wrap=True)
    table.add_column(style="dim")
    commands = [
        ("/init",         "Create CODEMITRA.md + codemitra.toml in current folder"),
        ("/run <cmd>",    "Run a shell command directly in the workspace (e.g. /run python main.py)"),
        ("/run --background <cmd>", "Start a long-running shell command in the background and keep using CodeMitra"),
        ("/plan <goal>",  "Set the active plan for this project (saved to .codemitra/plan.md)"),
        ("/plan",         "Show the current active plan"),
        ("/plan approve", "Approve the saved plan for execution"),
        ("/plan next",    "Execute exactly one approved pending plan step"),
        ("/plan run",     "Execute all approved pending plan steps"),
        ("/plan pause",   "Pause active plan execution without losing progress"),
        ("/brainstorm <topic>", "Brainstorm ideas in a lighter chat mode and save them to .codemitra/brainstorm.md"),
        ("/brainstorm",   "Show saved brainstorm notes"),
        ("/memory",       "Show saved workspace artifacts like context, plan, and brainstorm notes"),
        ("/context",      "Show live context-window usage, compact threshold, and session load"),
        ("/status",       "Show workspace, model, plan, approval, and session status"),
        ("/permissions",  "Show current execution policy, workspace scope, and tool restrictions"),
        ("/resume",       "Show the saved session summary, plan state, undo state, and recent activity"),
        ("/rename <name>", "Rename the current workspace session"),
        ("/mode [name]",  "Show or change session mode: read-only, plan, approve, auto"),
        ("/thinking on|off", "Show or hide raw reasoning panels when models emit them"),
        ("/model",        "Show the active chat and codegen models"),
        ("/model list",   "Show installed local Ollama models and highlight the active one"),
        ("/model remove <name>", "Delete a local Ollama model you no longer want"),
        ("/history",      "Show the recent saved conversation history from .codemitra/activity.md"),
        ("/diff",         "Show the current git diff or the last CodeMitra change set"),
        ("/review [staged]", "Review the current or staged git diff, or the last CodeMitra change set, for material issues"),
        ("/explain <file>", "Explain what a specific file does, including important flows and editing risks"),
        ("/symbols <name>", "Show symbol-focused code intelligence: definitions plus usages across the workspace"),
        ("/search <query>", "Search the web for public docs, references, tutorials, or other online information"),
        ("/open-url <url>", "Read and summarize a specific webpage"),
        ("/undo",         "Undo the last recorded file change set applied by CodeMitra"),
        ("/fix <cmd>",    "Run a bounded test-fix-retry loop for a failing command"),
        ("/tasks",        "List tracked background tasks and show their current status"),
        ("/tasks show <id>", "Show details and recent output for one background task"),
        ("/tasks stop <id>", "Stop a running background task"),
        ("/skills",       "List available CodeMitra skills discovered in this workspace"),
        ("/skills show <name>", "Show one skill's instructions"),
        ("/compact",      "Summarise + compress conversation history to free context window"),
        ("/hibernate",   "Save session memory, unload the active local model, clear chat history, and continue fresh"),
        ("/reset",        "Clear conversation history (memory files are kept)"),
        ("/help",         "Show this help"),
        ("exit / quit",   "Exit CodeMitra"),
    ]
    for cmd, desc in commands:
        table.add_row(cmd, desc)
    console.print(Panel(table, title="[bold cyan]Slash Commands[/bold cyan]", border_style="cyan"))


if __name__ == "__main__":
    cli()
