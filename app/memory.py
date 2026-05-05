"""Obsidian-compatible project memory for CodeMitra.

Files written to <workspace>/.codemitra/
  activity.md  — timestamped log of every conversation turn (daily-note style)
  context.md   — running project state, injected into the system prompt
  plan.md      — current active plan (populated by the planner agent later)

All files are plain Markdown — open the .codemitra/ folder as an Obsidian vault
to browse, search, and link between sessions.
"""

from __future__ import annotations

import pathlib
import textwrap
from datetime import datetime


# ── Paths ─────────────────────────────────────────────────────────────────────

_DIR = ".codemitra"
_ACTIVITY  = "activity.md"
_CONTEXT   = "context.md"
_PLAN      = "plan.md"


def _dir(workspace: str) -> pathlib.Path:
    d = pathlib.Path(workspace).resolve() / _DIR
    d.mkdir(exist_ok=True)
    return d


# ── Activity log ──────────────────────────────────────────────────────────────

def append_activity(workspace: str, user_msg: str, ai_summary: str) -> None:
    """Append one conversation turn to activity.md.

    Format (Obsidian daily-note style):
      ## YYYY-MM-DD
      ### HH:MM
      **You:** ...
      **CodeMitra:** ...
    """
    path = _dir(workspace) / _ACTIVITY
    now  = datetime.now()
    date_heading = f"## {now.strftime('%Y-%m-%d')}"
    time_heading  = f"### {now.strftime('%H:%M')}"

    # Trim long messages so the log stays readable
    user_short = _trim(user_msg, 300)
    ai_short   = _trim(ai_summary, 400)

    entry = (
        f"\n{time_heading}\n"
        f"**You:** {user_short}\n\n"
        f"**CodeMitra:** {ai_short}\n"
    )

    if path.exists():
        existing = path.read_text(encoding="utf-8")
        # Only insert the date heading once per day
        if date_heading not in existing:
            entry = f"\n{date_heading}\n{entry}"
        path.write_text(existing + entry, encoding="utf-8")
    else:
        header = textwrap.dedent(f"""\
            ---
            title: Activity Log
            tags: [codemitra, activity, log]
            ---

            # CodeMitra - Activity Log

            {date_heading}
        """)
        path.write_text(header + entry, encoding="utf-8")


# ── Context file ──────────────────────────────────────────────────────────────

_CONTEXT_TEMPLATE = textwrap.dedent("""\
    ---
    title: Project Context
    tags: [codemitra, context, memory]
    updated: {updated}
    ---

    # Project Context

    > Auto-maintained by CodeMitra. Edit freely - it is re-read at every startup.

    ## Last active
    {updated}

    ## Recent topics
    {topics}

    ## Notes
    <!-- Add anything you want CodeMitra to always remember about this project -->

""")


def load_context(workspace: str) -> str | None:
    """Return the contents of context.md, or None if it does not exist yet."""
    path = _dir(workspace) / _CONTEXT
    if path.exists():
        return path.read_text(encoding="utf-8")
    return None


def update_context(workspace: str, new_topic: str) -> None:
    """Prepend `new_topic` to the Recent topics list in context.md.

    Creates the file with a starter template if it does not exist.
    """
    path  = _dir(workspace) / _CONTEXT
    now   = datetime.now().strftime("%Y-%m-%d %H:%M")
    topic = _trim(new_topic, 120)

    if path.exists():
        text = path.read_text(encoding="utf-8")

        # Update the 'updated' frontmatter field
        text = _replace_field(text, "updated", now)

        # Prepend new topic under "## Recent topics"
        marker = "## Recent topics"
        if marker in text:
            idx = text.index(marker) + len(marker)
            bullet = f"\n- `{now}` {topic}"
            # Keep only the last 20 topic lines to avoid unbounded growth
            lines = text[idx:].splitlines()
            topic_lines = [l for l in lines if l.startswith("- `")]
            topic_lines = topic_lines[:19]  # keep 19 existing + 1 new
            rest_lines  = [l for l in lines if not l.startswith("- `")]
            new_topics  = bullet + "\n" + "\n".join(topic_lines)
            text = text[:idx] + new_topics + "\n" + "\n".join(rest_lines)
        path.write_text(text, encoding="utf-8")
    else:
        content = _CONTEXT_TEMPLATE.format(
            updated=now,
            topics=f"- `{now}` {topic}",
        )
        path.write_text(content, encoding="utf-8")


# ── Plan file ─────────────────────────────────────────────────────────────────

_PLAN_TEMPLATE = textwrap.dedent("""\
    ---
    title: Active Plan
    tags: [codemitra, plan]
    updated: {updated}
    ---

    # Active Plan

    > Managed by CodeMitra's planner. Use `/plan <goal>` to set or update.

    ## Goal
    {goal}

    ## Steps
    {steps}

    ## Completed
    <!-- CodeMitra will check off steps here as work progresses -->

""")


def load_plan(workspace: str) -> str | None:
    """Return current plan.md contents, or None."""
    path = _dir(workspace) / _PLAN
    if path.exists():
        return path.read_text(encoding="utf-8")
    return None


def write_plan(workspace: str, goal: str, steps: list[str]) -> pathlib.Path:
    """Write (or overwrite) plan.md with a new goal and step list."""
    path = _dir(workspace) / _PLAN
    now  = datetime.now().strftime("%Y-%m-%d %H:%M")
    steps_md = "\n".join(f"- [ ] {s}" for s in steps)
    content = _PLAN_TEMPLATE.format(updated=now, goal=goal, steps=steps_md)
    path.write_text(content, encoding="utf-8")
    return path


def mark_step_done(workspace: str, step_index: int) -> None:
    """Tick off step number `step_index` (0-based) in plan.md."""
    path = _dir(workspace) / _PLAN
    if not path.exists():
        return
    lines = path.read_text(encoding="utf-8").splitlines()
    unchecked = [i for i, l in enumerate(lines) if l.startswith("- [ ]")]
    if step_index < len(unchecked):
        i = unchecked[step_index]
        lines[i] = lines[i].replace("- [ ]", "- [x]", 1)
    path.write_text("\n".join(lines), encoding="utf-8")


# ── Init ──────────────────────────────────────────────────────────────────────

_ACTIVITY_TEMPLATE = textwrap.dedent("""\
    ---
    title: Activity Log
    tags: [codemitra, activity, log]
    ---

    # CodeMitra - Activity Log

    > One entry per conversation turn. Open this folder as an Obsidian vault.

""")

_OBSIDIAN_README = textwrap.dedent("""\
    # .codemitra vault

    This folder is managed by **CodeMitra** and doubles as an [Obsidian](https://obsidian.md) vault.

    | File | Purpose |
    |---|---|
    | `activity.md` | Timestamped log of every conversation turn |
    | `context.md`  | Running project state — injected into every session |
    | `plan.md`     | Active task plan with checkboxes |

    Open this folder in Obsidian for graph view, search, and daily-note navigation.
""")


def init_memory(workspace: str) -> list[str]:
    """Create the .codemitra/ vault skeleton during `codemitra init`.

    Returns a list of file paths that were created (skips existing files).
    """
    d = _dir(workspace)
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    project_name = pathlib.Path(workspace).resolve().name
    created: list[str] = []

    # activity.md
    activity_path = d / _ACTIVITY
    if not activity_path.exists():
        activity_path.write_text(_ACTIVITY_TEMPLATE, encoding="utf-8")
        created.append(str(activity_path.relative_to(pathlib.Path(workspace).resolve())))

    # context.md — pre-fill with project name as first note
    context_path = d / _CONTEXT
    if not context_path.exists():
        content = _CONTEXT_TEMPLATE.format(
            updated=now,
            topics=f"- `{now}` Project initialised",
        )
        # Inject project name into Notes section
        content = content.replace(
            "<!-- Add anything you want CodeMitra to always remember about this project -->",
            f"<!-- Add anything you want CodeMitra to always remember about this project -->\n"
            f"- Project: **{project_name}**",
        )
        context_path.write_text(content, encoding="utf-8")
        created.append(str(context_path.relative_to(pathlib.Path(workspace).resolve())))

    # plan.md — empty starter
    plan_path = d / _PLAN
    if not plan_path.exists():
        content = _PLAN_TEMPLATE.format(
            updated=now,
            goal="_No active goal. Use `/plan <goal>` to set one._",
            steps="- [ ] Define project goal",
        )
        plan_path.write_text(content, encoding="utf-8")
        created.append(str(plan_path.relative_to(pathlib.Path(workspace).resolve())))

    # README.md — Obsidian vault description
    readme_path = d / "README.md"
    if not readme_path.exists():
        readme_path.write_text(_OBSIDIAN_README, encoding="utf-8")
        created.append(str(readme_path.relative_to(pathlib.Path(workspace).resolve())))

    return created


# ── Helpers ───────────────────────────────────────────────────────────────────

def _trim(text: str, max_chars: int) -> str:
    text = text.strip().replace("\n", " ")
    if len(text) > max_chars:
        return text[:max_chars].rstrip() + "…"
    return text


def _replace_field(text: str, field: str, value: str) -> str:
    """Replace `field: <old>` in YAML frontmatter."""
    import re
    return re.sub(rf"^{field}:.*$", f"{field}: {value}", text, flags=re.MULTILINE)
