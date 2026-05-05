"""Planner Agent — breaks a goal into ordered steps and orchestrates execution.

The planner:
  1. Takes a high-level goal and breaks it into concrete, actionable steps.
  2. Writes the plan to .codemitra/plan.md.
  3. On each turn, reads the plan, picks the next pending step, and routes it
     to the appropriate agent (filesystem, shell, or reader).
  4. Marks steps done, updates the plan file, and summarises progress.

The planner itself does NOT execute code or touch files directly —
it generates a plan and hands off each step to the correct agent.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.table import Table
from rich.text import Text

from app import memory


# ─── Data model ───────────────────────────────────────────────────────────────

@dataclass
class Step:
    index: int
    text: str
    done: bool = False


@dataclass
class Plan:
    goal: str
    steps: list[Step] = field(default_factory=list)

    @property
    def pending(self) -> list[Step]:
        return [s for s in self.steps if not s.done]

    @property
    def completed(self) -> list[Step]:
        return [s for s in self.steps if s.done]

    @property
    def is_done(self) -> bool:
        return all(s.done for s in self.steps)


# ─── Parse plan.md into a Plan object ────────────────────────────────────────

def _parse_plan(workspace: str) -> Plan | None:
    raw = memory.load_plan(workspace)
    if not raw:
        return None

    goal_match = re.search(r"## Goal\n(.+)", raw)
    goal = goal_match.group(1).strip() if goal_match else "Unknown goal"

    steps: list[Step] = []
    for i, m in enumerate(re.finditer(r"- \[([ x])\] (.+)", raw)):
        done = m.group(1) == "x"
        text = m.group(2).strip()
        steps.append(Step(index=i, text=text, done=done))

    return Plan(goal=goal, steps=steps)


# ─── Generate a plan via the LLM ─────────────────────────────────────────────

_PLAN_PROMPT = """You are a senior software engineer creating an execution plan.

Given the goal and clarifying context below, output a numbered list of concrete, atomic steps.
Each step must:
- Be a single action (create X, run Y, install Z, read A, test B)
- Start with an imperative verb
- Be completable by one tool call
- Not exceed one sentence

Output ONLY the numbered list — no intro, no explanation, no markdown fences.
Example:
1. Create folder structure for the project
2. Create main.py with the entry point
3. Create requirements.txt with dependencies
4. Create virtual environment
5. Install packages from requirements.txt
6. Run pytest to verify the setup

Goal: {goal}

Clarifying context (use this to make the steps specific, not generic):
{context}
"""


def create_plan(llm, goal: str, workspace: str, context: str = "") -> Plan:
    """Ask the LLM to break a goal into steps, write plan.md, return Plan."""
    response = llm.invoke([HumanMessage(content=_PLAN_PROMPT.format(
        goal=goal,
        context=context if context else "None provided.",
    ))])
    raw = (response.content or "").strip()

    # Parse numbered list
    steps: list[str] = []
    for line in raw.splitlines():
        m = re.match(r"^\s*\d+[.)]\s+(.+)", line)
        if m:
            steps.append(m.group(1).strip())

    if not steps:
        # Fallback — treat each non-empty line as a step
        steps = [l.strip() for l in raw.splitlines() if l.strip()]

    memory.write_plan(workspace, goal, steps)
    return Plan(goal=goal, steps=[Step(index=i, text=s) for i, s in enumerate(steps)])


# ─── Render plan panel ────────────────────────────────────────────────────────

def render(plan: Plan) -> Panel:
    """Render the current plan as a Rich Panel."""
    table = Table.grid(padding=(0, 1))
    table.add_column(width=2)
    table.add_column()

    for step in plan.steps:
        if step.done:
            table.add_row("[green]✓[/green]", Text(step.text, style="dim strike"))
        else:
            table.add_row("[yellow]○[/yellow]", step.text)

    pending = len(plan.pending)
    done    = len(plan.completed)
    footer  = f"[dim]{done}/{len(plan.steps)} steps done[/dim]"

    from rich.console import Group
    content = Group(
        Text.from_markup(f"[bold]Goal:[/bold] {plan.goal}\n"),
        table,
        Text(""),
        Text.from_markup(footer),
    )

    border = "green" if plan.is_done else "yellow"
    title  = "[bold green]Plan complete ✓[/bold green]" if plan.is_done else "[bold yellow]Active Plan[/bold yellow]"
    return Panel(content, title=title, border_style=border)


# ─── Step router ─────────────────────────────────────────────────────────────

_ROUTER_PROMPT = """You are routing a single task step to the correct agent.

Step: {step}

Reply with EXACTLY one word — the agent name — from this list:
- filesystem  (create/write/delete/move files, install packages, git)
- shell       (run scripts, tests, linters, servers)
- reader      (read/search/analyse existing code without modifying)
- direct      (the answer can be given directly without any tool)

Reply with nothing else.
"""


def _route_step(llm, step_text: str) -> str:
    response = llm.invoke([HumanMessage(content=_ROUTER_PROMPT.format(step=step_text))])
    word = (response.content or "").strip().lower().split()[0] if response.content else "direct"
    return word if word in ("filesystem", "shell", "reader", "direct") else "direct"


# ─── Execute one step ─────────────────────────────────────────────────────────

def execute_step(
    llm,
    step: Step,
    workspace: str,
    console: Console | None = None,
    codegen_llm=None,
    reader_llm=None,
    shell_llm=None,
    direct_llm=None,
) -> str:
    """Route a single plan step to the right agent and return its summary."""
    from app.agents import filesystem, shell as shell_agent, reader as reader_agent

    agent_name = _route_step(llm, step.text)

    if console:
        console.print(
            f"  [dim]Step {step.index + 1}: routing to [bold]{agent_name}[/bold] agent[/dim]"
        )

    if agent_name == "filesystem":
        resp = filesystem.run(codegen_llm or llm, step.text, console=console)
        return resp.summary

    if agent_name == "shell":
        from app.agents.shell import run_agent
        return run_agent(shell_llm or llm, step.text, console=console)

    if agent_name == "reader":
        resp = reader_agent.run(reader_llm or llm, step.text, console=console)
        return resp.summary

    # direct — ask the LLM directly
    response = (direct_llm or llm).invoke([HumanMessage(content=step.text)])
    return (response.content or "").strip()


# ─── Main plan runner ─────────────────────────────────────────────────────────

def run_plan(
    llm,
    workspace: str,
    console: Console | None = None,
    max_steps: int | None = None,
    codegen_llm=None,
    reader_llm=None,
    shell_llm=None,
    direct_llm=None,
) -> str:
    """Execute all pending steps in the current plan. Returns a summary string."""
    plan = _parse_plan(workspace)
    if plan is None:
        return "No active plan. Use /plan <goal> to create one."

    if plan.is_done:
        return "All steps are already completed."

    summaries: list[str] = []
    steps_run = 0

    for step in plan.pending:
        if max_steps and steps_run >= max_steps:
            break

        if console:
            console.print(
                Panel(
                    f"[bold]{step.text}[/bold]",
                    title=f"[bold yellow]Step {step.index + 1} of {len(plan.steps)}[/bold yellow]",
                    border_style="yellow",
                )
            )

        result = execute_step(
            llm,
            step,
            workspace,
            console=console,
            codegen_llm=codegen_llm,
            reader_llm=reader_llm,
            shell_llm=shell_llm,
            direct_llm=direct_llm,
        )
        summaries.append(f"Step {step.index + 1} ({step.text}): {result[:300]}")
        memory.mark_step_done(workspace, step.index)
        steps_run += 1

        if console:
            console.print(f"  [green]✓ Step {step.index + 1} done[/green]\n")

    # Reload to get updated plan
    updated_plan = _parse_plan(workspace)
    if console and updated_plan:
        console.print(render(updated_plan))

    remaining = len(updated_plan.pending) if updated_plan else 0
    done_count = steps_run

    summary = (
        f"Executed {done_count} step(s). "
        f"{remaining} step(s) remaining.\n\n"
        + "\n".join(summaries)
    )
    return summary


# ─── Routing tool (for main LLM) ─────────────────────────────────────────────

def make_routing_tool(
    llm,
    workspace: str,
    console: Console | None = None,
    codegen_llm=None,
    reader_llm=None,
    shell_llm=None,
    direct_llm=None,
):
    """Return a LangChain tool the main LLM can call to continue the active plan."""
    @tool
    def execute_plan(request: str) -> str:
        """
        Execute the next step(s) of the active project plan.
        Use when the user asks to continue, proceed, execute the plan,
        or work on the next task. Pass the full user request unchanged.
        """
        return run_plan(
            llm,
            workspace,
            console=console,
            max_steps=1,
            codegen_llm=codegen_llm,
            reader_llm=reader_llm,
            shell_llm=shell_llm,
            direct_llm=direct_llm,
        )
    return execute_plan
