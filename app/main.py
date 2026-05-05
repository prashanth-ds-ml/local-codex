
import pathlib
import re
import subprocess
import sys
import traceback
import getpass

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

from app.llm import get_cloud_llm, get_local_llm
from app.prompts import SYSTEM_PROMPT
from app.agents import filesystem
from app.agents import shell as shell_agent
from app.agents import reader as reader_agent
from app.agents import planner as planner_agent
from app.agents.response import render
from app import config, memory

cli = typer.Typer(invoke_without_command=True, add_completion=False)


console = Console()

try:
    # prefer direct import
    from misc.ascii import generate_title_art
except Exception:
    # ensure project root is on sys.path when running as script
    import sys
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.append(str(root))
    from misc.ascii import generate_title_art




def show_banner():
    try:
        title = generate_title_art("CodeMitra", cols=96, rows=8)
    except Exception:
        from rich.text import Text
        title = Text("  CodeMitra  ", style="bold green")

    from rich.console import Group
    from rich.text import Text as RichText
    subtitle = Align.center(RichText("Your local AI coding companion", style="dim"))
    p1 = Align.center(RichText.assemble(("✦", "green"), ("  Powered by Ollama", "dim")))
    p2 = Align.center(RichText.assemble(("✦", "green"), ("  Runs 100% offline", "dim")))
    p3 = Align.center(RichText.assemble(("✦", "green"), ("  No data leaves your machine", "dim")))
    hint = Align.center(RichText.assemble(
        ("Type ", "dim"), ("exit", "green"), (" or ", "dim"), ("quit", "green"), (" to leave", "dim")
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
                border_style="green",
                padding=(1, 4),
                width=110,
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
memory_enabled = false
require_diff_approval = false
auto_compact_threshold = 8000  # auto-compact when session tokens exceed this
ollama_api_key = ""          # optional; leave empty to be prompted at startup
ollama_local_base_url = "http://localhost:11434"
ollama_cloud_base_url = "https://ollama.com"
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
    "/init", "/run", "/plan", "/memory", "/context", "/compact", "/reset", "/help",
    "exit", "quit",
]


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


def _pick_model(cfg: dict) -> str:
    """Return the model to use: from config if set, otherwise prompt the user."""
    configured = cfg.get("local_model") or cfg.get("model")
    if configured:
        console.print(f"[dim cyan]  ✔  Local model: {configured}[/dim cyan]")
        return configured

    models = config.list_local_models()
    if not models:
        console.print("[red]No local Ollama models found. Run 'ollama pull <model>' first.[/red]")
        raise SystemExit(1)

    console.print("\n[bold cyan]Available models:[/bold cyan]")
    for i, m in enumerate(models, 1):
        console.print(f"  [cyan]{i}[/cyan]  {m}")

    while True:
        choice = console.input("\n[bold]Pick a model (number or name):[/bold] ").strip()
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(models):
                return models[idx]
        elif choice in models:
            return choice
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
        "[dim]/run <cmd>[/dim][dim]  ·  [/dim]"
        "[dim]/plan <goal>[/dim][dim]  ·  [/dim]"
        "[dim]Tab[/dim][dim] to complete  ·  [/dim]"
        "[dim]↑↓[/dim][dim] history[/dim]"
    )
    console.print()


def _chat():
    show_banner()

    cfg = config.load()
    model = _pick_model(cfg)
    codegen_model = _resolve_codegen_model(cfg)
    temperature = cfg.get("temperature", 0.2)

    # Lock the filesystem agent to the current project folder
    filesystem.configure(workspace=cfg["workspace"], confirm_fn=_confirm_tool)
    reader_agent.configure(workspace=cfg["workspace"])

    # Configure the shell agent
    shell_agent.configure(
        workspace=cfg["workspace"],
        stream_to_console=True,
        confirm_fn=_confirm_shell,
    )

    # Build system prompt, appending project rules + memory context
    system_prompt = SYSTEM_PROMPT
    if cfg.get("rules"):
        system_prompt += f"\n\n## Project Rules (from CODEMITRA.md)\n{cfg['rules']}"
        console.print("[dim cyan]  ✦  Project rules loaded from CODEMITRA.md[/dim cyan]")

    ctx_text = memory.load_context(cfg["workspace"])
    if ctx_text:
        system_prompt += f"\n\n## Project Memory (from .codemitra/context.md)\n{ctx_text}"
        console.print("[dim cyan]  ✦  Project memory loaded from .codemitra/context.md[/dim cyan]")

    plan_text = memory.load_plan(cfg["workspace"])
    if plan_text:
        system_prompt += f"\n\n## Active Plan (from .codemitra/plan.md)\n{plan_text}"
        console.print("[dim cyan]  ✦  Active plan loaded from .codemitra/plan.md[/dim cyan]")

    if ctx_text or plan_text:
        console.print()

    local_llm = get_local_llm(
        model,
        temperature,
        base_url=cfg.get("ollama_local_base_url"),
    )
    cloud_api_key = _resolve_cloud_api_key(cfg)
    codegen_llm = local_llm
    if cloud_api_key:
        codegen_llm = get_cloud_llm(
            codegen_model,
            temperature,
            api_key=cloud_api_key,
            base_url=cfg.get("ollama_cloud_base_url"),
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
    main_llm = local_llm.bind_tools([setup_tool, shell_tool, reader_tool, planner_tool])

    # ── Hint bar + prompt setup ───────────────────────────────────────────────
    _print_hint_bar()
    project_name = pathlib.Path(cfg["workspace"]).name
    model_short = model.split(":")[0]  # strip tag for brevity
    prompt_str = f"\n[{project_name}] ({model_short})> "
    completer = _make_completer(cfg["workspace"])
    session = PromptSession(history=InMemoryHistory(), completer=completer)
    messages = [SystemMessage(content=system_prompt)]
    sess_in = sess_out = 0  # cumulative session token counts

    while True:
        user_input = session.prompt(prompt_str)

        if user_input.strip() in ["/exit", "exit", "quit"]:
            console.print("[yellow]Goodbye.[/yellow]")
            break

        if not user_input.strip():
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
            _cmd_plan(user_input, cfg["workspace"], llm=local_llm)
            continue

        if cmd in ("/memory", "/context"):
            _cmd_memory(cfg["workspace"])
            continue

        if cmd == "/compact":
            messages = _compact(local_llm, messages, system_prompt)
            sess_in = sess_out = 0
            continue

        if cmd.startswith("/run "):
            raw_cmd = user_input.strip()[5:].strip()
            _cmd_run(raw_cmd, cfg["workspace"])
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
            if thinking:
                console.print(
                    Panel(
                        f"[dim italic]{thinking[:3000]}{'…' if len(thinking) > 3000 else ''}[/dim italic]",
                        title="[dim]Thinking[/dim]",
                        border_style="dim",
                        padding=(0, 1),
                    )
                )

            ai_reply = ""

            if response.tool_calls:
                for tc in response.tool_calls:
                    request = tc["args"].get("request", user_input)

                    if tc["name"] == "run_command":
                        # ── Shell Agent ───────────────────────────────────────
                        console.print(
                            f"\n  [bold blue]▶ Shell Agent[/bold blue]  "
                            f"[dim]{request[:80]}[/dim]\n"
                        )
                        shell_result = shell_agent.execute(
                            command=_extract_command(request),
                            cwd=None,
                            console=console,
                        )
                        console.print(shell_agent.render(shell_result))
                        messages.append(ToolMessage(content=shell_result.to_llm_summary(), tool_call_id=tc["id"]))
                        ai_reply = shell_result.to_llm_summary()
                    elif tc["name"] == "read_codebase":
                        # ── Code Reader Agent ─────────────────────────────────
                        console.print(
                            f"\n  [bold magenta]▶ Code Reader[/bold magenta]  "
                            f"[dim]{request[:80]}[/dim]\n"
                        )
                        reader_resp = reader_agent.run(local_llm, request, console=console)
                        turn_in  += reader_resp.tokens_in
                        turn_out += reader_resp.tokens_out
                        messages.append(ToolMessage(content=reader_resp.summary, tool_call_id=tc["id"]))
                        console.print(reader_agent.render(reader_resp))
                        ai_reply = reader_resp.summary
                    elif tc["name"] == "execute_plan":
                        # ── Planner Agent ─────────────────────────────────────
                        console.print(
                            f"\n  [bold yellow]▶ Planner[/bold yellow]  "
                            f"[dim]{request[:80]}[/dim]\n"
                        )
                        plan_summary = planner_agent.run_plan(
                            local_llm,
                            cfg["workspace"],
                            console=console,
                            max_steps=1,
                            codegen_llm=codegen_llm,
                            reader_llm=local_llm,
                            shell_llm=local_llm,
                            direct_llm=local_llm,
                        )
                        messages.append(ToolMessage(content=plan_summary, tool_call_id=tc["id"]))
                        ai_reply = plan_summary
                    else:
                        # ── Filesystem Agent ──────────────────────────────────
                        console.print(
                            f"\n  [bold cyan]▶ Filesystem Agent[/bold cyan]  "
                            f"[dim]{request[:80]}[/dim]\n"
                        )
                        agent_resp = filesystem.run(codegen_llm, request, console=console)
                        turn_in += agent_resp.tokens_in
                        turn_out += agent_resp.tokens_out
                        messages.append(ToolMessage(content=agent_resp.summary, tool_call_id=tc["id"]))
                        console.print(render(agent_resp))
                        ai_reply = agent_resp.summary

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
                messages = _compact(local_llm, messages, system_prompt)
                sess_in = sess_out = 0

            # ── Persist to memory ─────────────────────────────────────────
            if ai_reply:
                memory.append_activity(cfg["workspace"], user_input, ai_reply)
                memory.update_context(cfg["workspace"], user_input)

        except KeyboardInterrupt:
            console.print("\n[dim]Interrupted.[/dim]")
        except Exception as e:
            _log_error(cfg["workspace"], e)
            console.print(
                Panel(
                    f"[red]⚠  {_friendly_error(e)}[/red]\n"
                    f"[dim](Full trace saved to .codemitra/errors.log)[/dim]",
                    title="[bold red]Error[/bold red]",
                    border_style="red",
                )
            )


def _cmd_plan(raw: str, workspace: str, llm=None) -> None:
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
        return

    if llm is not None:
        from app.agents import brainstorm as brainstorm_agent
        context = brainstorm_agent.run(llm, goal, console)
        with console.status("[bold green]Generating plan...[/bold green]"):
            plan = planner_agent.create_plan(llm, goal, workspace, context=context)
        console.print(f"[dim cyan]  ✦  Plan written to .codemitra/plan.md[/dim cyan]")
        console.print(planner_agent.render(plan))
        console.print("[dim]Use [cyan]/plan[/cyan] to review or type [cyan]continue[/cyan] to execute next step.[/dim]")
    else:
        # Fallback: write a generic plan without AI step generation
        path = memory.write_plan(workspace, goal=goal, steps=[
            "Understand current codebase structure",
            "Break goal into sub-tasks",
            "Implement each sub-task step by step",
            "Test and verify",
        ])
        console.print(f"[dim cyan]  ✦  Plan written to {path.relative_to(pathlib.Path(workspace))}[/dim cyan]")
        plan = planner_agent._parse_plan(workspace)
        if plan:
            console.print(planner_agent.render(plan))


def _cmd_memory(workspace: str) -> None:
    """Handle `/memory` — show current context.md and plan.md."""
    ctx = memory.load_context(workspace)
    plan = memory.load_plan(workspace)
    if not ctx and not plan:
        console.print("[dim]No memory yet. Start chatting and it will build automatically.[/dim]")
        return
    if ctx:
        console.print(Panel(ctx, title="[bold cyan].codemitra/context.md[/bold cyan]", border_style="cyan"))
    if plan:
        console.print(Panel(plan, title="[bold cyan].codemitra/plan.md[/bold cyan]", border_style="cyan"))


def _confirm_shell(command: str) -> bool:
    """Ask the user before the shell agent runs any command."""
    from rich.text import Text
    console.print()
    console.print(
        Panel(
            Text.assemble(
                ("Command: ", "dim"),
                (command, "bold yellow"),
                ("\n\nApprove? ", "dim"),
                ("[Y/n] ", "bold"),
            ),
            title="[bold yellow]\u26a1 Run shell command[/bold yellow]",
            border_style="yellow",
            padding=(0, 2),
        )
    )
    try:
        answer = console.input("  ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        answer = "n"
    approved = answer in ("", "y", "yes")
    console.print(f"  {'[green]✔ Approved[/green]' if approved else '[red]✘ Skipped[/red]'}")
    return approved


def _cmd_run(command: str, workspace: str) -> None:
    """/run <command> — execute a command directly in the workspace."""
    if not command:
        console.print("[dim]Usage: [cyan]/run <command>[/cyan]  e.g. /run python main.py[/dim]")
        return
    console.print()
    result = shell_agent.execute(command=command, cwd=workspace, console=console)
    console.print(shell_agent.render(result))


def _extract_command(request: str) -> str:
    """Pull a bare shell command out of a natural-language request.

    Looks for backtick-quoted text first, then takes the whole request as-is
    so the shell agent's LLM loop can handle it directly.
    """
    import re
    match = re.search(r"`([^`]+)`", request)
    return match.group(1) if match else request


def _confirm_tool(tool_name: str, args: dict) -> bool:
    """Ask the user before the filesystem agent executes a destructive tool."""
    from rich.text import Text
    _LABELS = {
        "delete_file":   ("Delete file",   "red"),
        "delete_folder": ("Delete folder", "red"),
        "move_file":     ("Move / rename",  "yellow"),
    }
    label, colour = _LABELS.get(tool_name, (tool_name, "yellow"))

    if tool_name == "move_file":
        detail = f"{args.get('src', '?')}  →  {args.get('dest', '?')}"
    else:
        detail = args.get("path", "?")

    console.print()
    console.print(
        Panel(
            Text.assemble(
                ("Action:  ", "dim"),
                (label, f"bold {colour}"),
                ("\nTarget:  ", "dim"),
                (detail, "bold"),
                ("\n\nApprove? ", "dim"),
                ("[y/N] ", "bold"),
            ),
            title=f"[bold {colour}]⚠  Destructive operation[/bold {colour}]",
            border_style=colour,
            padding=(0, 2),
        )
    )
    try:
        answer = console.input("  ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        answer = "n"
    approved = answer in ("y", "yes")
    console.print(f"  {'[green]✔ Approved[/green]' if approved else '[red]✘ Skipped[/red]'}")
    return approved


# ── Tokens at which auto-compact kicks in ────────────────────────────────────
_AUTO_COMPACT_THRESHOLD = 8_000   # overridden at runtime from codemitra.toml


def _compact(llm, messages: list, system_prompt: str) -> list:
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
        ("/plan <goal>",  "Set the active plan for this project (saved to .codemitra/plan.md)"),
        ("/plan",         "Show the current active plan"),
        ("/memory",       "Show project context + active plan"),
        ("/compact",      "Summarise + compress conversation history to free context window"),
        ("/reset",        "Clear conversation history (memory files are kept)"),
        ("/help",         "Show this help"),
        ("exit / quit",   "Exit CodeMitra"),
    ]
    for cmd, desc in commands:
        table.add_row(cmd, desc)
    console.print(Panel(table, title="[bold cyan]Slash Commands[/bold cyan]", border_style="cyan"))


if __name__ == "__main__":
    cli()