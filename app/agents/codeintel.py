"""Code Intelligence Agent — symbol-focused definitions and references."""
from __future__ import annotations

from dataclasses import dataclass

from rich.markdown import Markdown
from rich.panel import Panel

from app.agents import reader as reader_agent


@dataclass
class CodeIntelResponse:
    symbol: str
    summary: str


def run(workspace: str, symbol: str) -> CodeIntelResponse:
    reader_agent.configure(workspace=workspace)
    definition = reader_agent.find_definition.invoke({"name": symbol, "path": workspace})
    usages = reader_agent.grep_symbol.invoke({"symbol": symbol, "path": workspace})

    lines = [
        f"## Symbol: `{symbol}`",
        "",
        "### Definitions",
        definition if isinstance(definition, str) else str(definition),
        "",
        "### Usages",
        usages if isinstance(usages, str) else str(usages),
    ]
    return CodeIntelResponse(symbol=symbol, summary="\n".join(lines))


def render(response: CodeIntelResponse) -> Panel:
    return Panel(
        Markdown(response.summary),
        title="[bold cyan]Code Intelligence[/bold cyan]",
        border_style="cyan",
    )
