"""Explain Agent — explains a specific file clearly and concisely."""
from __future__ import annotations

import pathlib
from dataclasses import dataclass

from langchain_core.messages import HumanMessage, SystemMessage
from rich.markdown import Markdown
from rich.panel import Panel

from app.agents import reader as reader_agent


_SYSTEM_PROMPT = """You are the Explain Agent inside CodeMitra.

Your job is to explain a specific file in a way that is useful to an engineer joining the codebase.

Rules:
1. Explain what the file is responsible for.
2. Call out the most important functions, classes, or flows.
3. Mention meaningful dependencies or side effects.
4. Mention risks, quirks, or things to be careful about when editing it.
5. Be concise and structured.
"""


@dataclass
class ExplainResponse:
    path: str
    summary: str
    tokens_in: int = 0
    tokens_out: int = 0


def _resolve_target(workspace: str, raw_path: str) -> pathlib.Path:
    target = pathlib.Path(raw_path)
    if not target.is_absolute():
        target = pathlib.Path(workspace) / target
    return target.resolve()


def run(llm, workspace: str, raw_path: str) -> ExplainResponse:
    target = _resolve_target(workspace, raw_path)
    reader_agent.configure(workspace=workspace)
    file_text = reader_agent.read_file.invoke({"path": str(target)})
    if isinstance(file_text, str) and file_text.startswith("✗"):
        return ExplainResponse(path=str(target), summary=file_text)

    response = llm.invoke([
        SystemMessage(content=_SYSTEM_PROMPT),
        HumanMessage(
            content=(
                f"Workspace: {workspace}\n"
                f"File: {target}\n\n"
                f"File contents:\n{file_text}"
            )
        ),
    ])
    meta = getattr(response, "usage_metadata", None) or {}
    summary = (response.content or "").strip() or f"Could not explain `{target.name}` clearly."
    return ExplainResponse(
        path=str(target),
        summary=summary,
        tokens_in=meta.get("input_tokens", 0),
        tokens_out=meta.get("output_tokens", 0),
    )


def render(response: ExplainResponse) -> Panel:
    return Panel(
        Markdown(response.summary),
        title="[bold magenta]Explain[/bold magenta]",
        border_style="magenta",
    )
