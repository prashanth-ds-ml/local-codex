"""Review Agent — reviews current changes and surfaces actionable issues."""
from __future__ import annotations

from dataclasses import dataclass

from langchain_core.messages import HumanMessage, SystemMessage
from rich.markdown import Markdown
from rich.panel import Panel


_SYSTEM_PROMPT = """You are the Review Agent inside CodeMitra.

Your job is to review a code diff or change set and report only meaningful issues.

Rules:
1. Focus on correctness, regressions, edge cases, safety, and missing validation.
2. Ignore style, formatting, naming preferences, and minor polish.
3. If there are no material issues, say exactly: No material issues found.
4. Keep the review concise and actionable.
5. When possible, mention the affected file or change area.
"""


@dataclass
class ReviewResponse:
    request: str
    source: str
    summary: str
    tokens_in: int = 0
    tokens_out: int = 0


def run(llm, request: str, review_input: str, *, source: str = "current changes") -> ReviewResponse:
    response = llm.invoke([
        SystemMessage(content=_SYSTEM_PROMPT),
        HumanMessage(
            content=(
                f"Review source: {source}\n\n"
                f"User request: {request}\n\n"
                f"Changes to review:\n{review_input}"
            )
        ),
    ])
    meta = getattr(response, "usage_metadata", None) or {}
    summary = (response.content or "").strip() or "No material issues found."
    return ReviewResponse(
        request=request,
        source=source,
        summary=summary,
        tokens_in=meta.get("input_tokens", 0),
        tokens_out=meta.get("output_tokens", 0),
    )


def render(response: ReviewResponse) -> Panel:
    return Panel(
        Markdown(response.summary),
        title="[bold cyan]Review[/bold cyan]",
        border_style="cyan",
    )
