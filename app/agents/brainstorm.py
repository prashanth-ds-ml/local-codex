"""Brainstorm Agent — iterative Q&A to clarify a goal before planning.

Mirrors the brainstorm loop from agents-academy Project 1, adapted for
CodeMitra's ChatOllama LLM and Rich terminal UI.

Usage:
    from app.agents.brainstorm import run as brainstorm
    context = brainstorm(llm, goal, console)
    # context is a string of all Q&A collected — pass to create_plan
"""
from __future__ import annotations

import re

from langchain_core.messages import HumanMessage, SystemMessage
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.text import Text

_SYSTEM_PROMPT = """\
You are a sharp goal analyst helping clarify a goal before planning.

INSTRUCTIONS:
- Think through what you already understand and what you can reasonably assume.
- Only ask questions you genuinely cannot answer yourself — true blockers.
- Do NOT re-summarize previous answers. Do NOT repeat context already given.
- Max 1-3 high-value questions per round.
- If you have enough context to make a great plan, output READY_TO_PLAN.

OUTPUT — choose one of these two forms only:

Form A (need more info):
THINKING:
[your brief reasoning about what is still unclear]
QUESTIONS:
1. [first question]
2. [second question]

Form B (enough context):
THINKING:
[one sentence on what you understand]
READY_TO_PLAN

Output only Form A or Form B. Nothing else.\
"""

_MAX_ROUNDS = 5


def _build_message(goal: str, history: str) -> str:
    return (
        f"Goal: {goal}\n\n"
        f"Previous Q&A:\n{history if history else 'None yet.'}"
    )


def _parse_response(text: str) -> tuple[str, str, bool]:
    """Return (thinking, questions_text, is_ready)."""
    ready = "READY_TO_PLAN" in text
    thinking = ""
    questions = ""

    if "THINKING:" in text:
        ts = text.index("THINKING:") + len("THINKING:")
        if "QUESTIONS:" in text:
            thinking  = text[ts : text.index("QUESTIONS:")].strip()
            questions = text[text.index("QUESTIONS:") + len("QUESTIONS:") :].strip()
        elif "READY_TO_PLAN" in text:
            thinking  = text[ts : text.index("READY_TO_PLAN")].strip()
        else:
            thinking = text[ts:].strip()
    else:
        questions = text.strip()

    return thinking, questions, ready


def _extract_questions(questions_text: str) -> list[str]:
    return [
        line.strip()
        for line in questions_text.splitlines()
        if re.match(r"^\d+[\.\)]\s+.+", line.strip())
    ]


def run(llm, goal: str, console: Console) -> str:
    """
    Run an interactive brainstorm loop.
    Returns a string of all Q&A collected (the 'context' for the planner).
    """
    history_entries: list[str] = []
    round_num = 0

    console.print()
    console.print(Rule("[bold cyan]Brainstorming[/bold cyan]", style="cyan"))
    console.print()
    console.print(
        "  [dim]Before planning, CodeMitra will ask a few questions to build a better plan.[/dim]"
    )
    console.print()

    while round_num < _MAX_ROUNDS:
        round_num += 1
        history_text = "\n\n".join(history_entries) if history_entries else "None yet."

        messages = [
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(content=_build_message(goal, history_text)),
        ]

        with console.status("  [dim italic]Analysing goal...[/dim italic]", spinner="dots"):
            response = llm.invoke(messages)

        text = (response.content or "").strip()
        thinking, questions_text, ready = _parse_response(text)

        if thinking:
            console.print(
                Panel(
                    Text(thinking, style="dim italic"),
                    border_style="dim",
                    padding=(0, 2),
                    title="[dim]thinking[/dim]",
                    title_align="right",
                )
            )
            console.print()

        if ready or not questions_text.strip():
            console.print(
                Text("  ✓ Enough context — moving to plan generation.", style="green bold")
            )
            console.print()
            break

        question_lines = _extract_questions(questions_text)
        if not question_lines:
            console.print(
                Text("  ✓ Enough context — moving to plan generation.", style="green bold")
            )
            console.print()
            break

        if round_num > 1:
            console.print(Rule(f"[dim]Round {round_num}[/dim]", style="dim"))
            console.print()

        round_qa: list[str] = []
        for line in question_lines:
            console.print(f"  [bold white]{line}[/bold white]", highlight=False)
            try:
                answer = console.input("  [dim cyan]›[/dim cyan] ").strip()
            except (EOFError, KeyboardInterrupt):
                answer = "no answer given"
            round_qa.append(f"{line}\nAnswer: {answer or 'no answer given'}")
            console.print()

        history_entries.append("\n\n".join(round_qa))

    console.print(Rule(style="dim cyan"))
    console.print()
    return "\n\n".join(history_entries)
