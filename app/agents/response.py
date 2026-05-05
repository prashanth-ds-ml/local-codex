from __future__ import annotations

from dataclasses import dataclass, field

from rich.console import Group
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text


# ─── Data model ───────────────────────────────────────────────────────────────

@dataclass
class ToolResult:
    tool: str
    args: dict
    output: str

    @property
    def ok(self) -> bool:
        return self.output.startswith("✓")

    @property
    def label(self) -> str:
        return _extract_label(self.tool, self.args)


@dataclass
class AgentResponse:
    request: str
    steps: list[ToolResult] = field(default_factory=list)
    summary: str = ""
    tokens_in: int = 0
    tokens_out: int = 0

    @property
    def ok_count(self) -> int:
        return sum(1 for s in self.steps if s.ok)

    @property
    def err_count(self) -> int:
        return sum(1 for s in self.steps if not s.ok)


# ─── Label extractor ──────────────────────────────────────────────────────────

def _extract_label(tool: str, args: dict) -> str:
    match tool:
        case "move_file":
            return f"{args.get('src', '')}  →  {args.get('dest', '')}"
        case "create_venv":
            return args.get("project_path", "")
        case "install_packages":
            path = args.get("project_path", "")
            pkgs = args.get("packages")
            suffix = f"[{', '.join(pkgs)}]" if pkgs else "[from requirements.txt]"
            return f"{path}  {suffix}"
        case "run_command":
            cmd = args.get("command", "")
            cwd = args.get("cwd", "")
            return f"{cmd}  (in {cwd})" if cwd and cwd != "." else cmd
        case _:
            return args.get("path", args.get("project_path", ""))


# ─── Panel title ──────────────────────────────────────────────────────────────

def _panel_title(response: AgentResponse) -> str:
    """Derive a context-aware title from the dominant tool called."""
    tools_used = {s.tool for s in response.steps}
    if tools_used & {"git_status", "git_diff", "git_commit"}:
        return "Git"
    if tools_used & {"install_packages", "create_venv"}:
        return "Installing packages"
    if tools_used & {"delete_file", "delete_folder"}:
        return "Removing files"
    if tools_used & {"move_file"}:
        return "Moving files"
    if tools_used & {"create_file", "create_folder"}:
        return "Creating files"
    if tools_used & {"read_file", "list_directory"}:
        return "Reading project"
    return "Setup Agent"


# ─── Renderer ─────────────────────────────────────────────────────────────────

def render(response: AgentResponse) -> Panel:
    """Build a Rich Panel from an AgentResponse."""
    parts: list = []

    # ── Request ──
    parts.append(
        Text.from_markup(
            f"[dim]>[/dim] [italic]{response.request}[/italic]"
        )
    )
    parts.append(Text(""))

    # ── Steps ──
    if response.steps:
        parts.append(Rule(title="steps", style="dim cyan", align="left"))
        parts.append(Text(""))

        grid = Table.grid(padding=(0, 1))
        grid.add_column(width=3, no_wrap=True)   # icon
        grid.add_column(width=20, style="dim")   # tool name
        grid.add_column()                        # label / detail

        for step in response.steps:
            if step.ok:
                icon = Text("✓", style="bold green")
                label = Text(step.label, style="cyan")
            else:
                icon = Text("✗", style="bold red")
                # On failure: first line of output only (no walls of text)
                first_line = step.output.lstrip("✗").strip().splitlines()[0]
                label = Text(first_line[:120], style="red")

            grid.add_row(icon, step.tool, label)

        parts.append(grid)
        parts.append(Text(""))

    # ── Summary ──
    if response.summary:
        parts.append(Rule(title="summary", style="dim cyan", align="left"))
        parts.append(Text(""))
        parts.append(Text(response.summary))
        parts.append(Text(""))

    # ── Footer ──
    ok, err = response.ok_count, response.err_count
    footer = Text()
    footer.append(f"  {ok} done", style="bold green")
    footer.append("  ·  ", style="dim")
    footer.append(
        f"{err} error{'s' if err != 1 else ''}",
        style="bold red" if err else "dim",
    )
    parts.append(footer)

    return Panel(
        Group(*parts),
        title=f"[bold cyan]{_panel_title(response)}[/bold cyan]",
        border_style="cyan",
        padding=(1, 2),
    )
