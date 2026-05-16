"""Session Agent — manages session naming and resume summaries."""
from __future__ import annotations

import pathlib
from dataclasses import dataclass

from rich.markdown import Markdown
from rich.panel import Panel

from app import memory


@dataclass
class SessionSnapshot:
    name: str
    workspace: str
    recent_history: list[dict[str, str]]
    plan_loaded: bool
    brainstorm_loaded: bool
    context_loaded: bool
    last_change_summary: str
    plan_execution: dict | None
    active_plan_step: dict | None
    last_compaction: dict | None


def ensure_session(workspace: str) -> dict:
    root = pathlib.Path(workspace).resolve()
    return memory.ensure_session_metadata(workspace, default_name=root.name)


def rename_session(workspace: str, new_name: str) -> dict:
    current = ensure_session(workspace)
    updated = {
        **current,
        "name": new_name.strip(),
    }
    memory.save_session_metadata(workspace, updated)
    return memory.load_session_metadata(workspace) or updated


def load_snapshot(workspace: str) -> SessionSnapshot:
    metadata = ensure_session(workspace)
    history = memory.load_recent_activity(workspace, limit=3)
    change_set = memory.load_last_change_set(workspace)
    entries = (change_set or {}).get("entries") or []
    last_change_summary = (
        f"{len(entries)} step{'s' if len(entries) != 1 else ''} available for undo"
        if entries else
        "None"
    )
    return SessionSnapshot(
        name=metadata.get("name", pathlib.Path(workspace).resolve().name),
        workspace=str(pathlib.Path(workspace).resolve()),
        recent_history=history,
        plan_loaded=bool(memory.load_plan(workspace)),
        brainstorm_loaded=bool(memory.load_brainstorm(workspace)),
        context_loaded=bool(memory.load_context(workspace)),
        last_change_summary=last_change_summary,
        plan_execution=metadata.get("plan_execution"),
        active_plan_step=metadata.get("active_plan_step"),
        last_compaction=metadata.get("last_compaction"),
    )


def build_resume_reply(workspace: str) -> str:
    snapshot = load_snapshot(workspace)
    lines = [
        "## Session resume",
        "",
        f"- **Session:** `{snapshot.name}`",
        f"- **Workspace:** `{snapshot.workspace}`",
        f"- **Plan:** {'Loaded' if snapshot.plan_loaded else 'No active plan'}",
        f"- **Brainstorm notes:** {'Saved' if snapshot.brainstorm_loaded else 'None yet'}",
        f"- **Context:** {'Loaded' if snapshot.context_loaded else 'Not loaded yet'}",
        f"- **Undo state:** {snapshot.last_change_summary}",
    ]
    if snapshot.plan_execution:
        execution = snapshot.plan_execution
        approved = "approved" if execution.get("approved") else "not approved"
        status = execution.get("status", "draft")
        lines.append(f"- **Plan execution:** `{approved}` · `{status}`")
    if snapshot.active_plan_step:
        step = snapshot.active_plan_step
        index = int(step.get("index", 0)) + 1
        status = step.get("status", "unknown")
        text = step.get("text", "")
        next_action = "Use `/plan next` to continue." if status in {"interrupted", "paused"} else "Use `/plan` to review or `/plan next` to continue."
        lines.append(f"- **Plan checkpoint:** Step {index} `{status}` - {text}")
        lines.append(f"- **Next plan action:** {next_action}")
    if snapshot.last_compaction:
        compact = snapshot.last_compaction
        reason = compact.get("reason", "manual")
        turns = compact.get("turns_compacted", 0)
        stamp = compact.get("compacted_at", "recently")
        usage = compact.get("usage_tokens_before")
        usage_text = f", {usage:,} tokens before compact" if isinstance(usage, int) else ""
        lines.append(f"- **Last compaction:** `{reason}` at {stamp} ({turns} turn{'s' if turns != 1 else ''}{usage_text})")
    if snapshot.recent_history:
        lines.extend(["", "## Recent activity", ""])
        for entry in snapshot.recent_history:
            stamp = " ".join(part for part in (entry.get("date"), entry.get("time")) if part)
            lines.append(f"- **{stamp}** — {entry.get('user', '')}")
    else:
        lines.extend(["", "## Recent activity", "", "- No saved activity yet."])
    return "\n".join(lines)


def render_resume(reply: str) -> Panel:
    return Panel(
        Markdown(reply),
        title="[bold cyan]Session Resume[/bold cyan]",
        border_style="cyan",
    )
