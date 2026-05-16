"""Obsidian-compatible project memory for CodeMitra.

Files written to <workspace>/.codemitra/
  activity.md  — timestamped log of every conversation turn (daily-note style)
  context.md   — running project state, injected into the system prompt
  plan.md      — current active plan (populated by the planner agent later)

All files are plain Markdown — open the .codemitra/ folder as an Obsidian vault
to browse, search, and link between sessions.
"""

from __future__ import annotations

import json
import pathlib
import textwrap
from datetime import datetime


# ── Paths ─────────────────────────────────────────────────────────────────────

_DIR = ".codemitra"
_ACTIVITY  = "activity.md"
_CONTEXT   = "context.md"
_PLAN      = "plan.md"
_BRAINSTORM = "brainstorm.md"
_LAST_CHANGE = "last_change.json"
_SESSION = "session.json"


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


def load_brainstorm(workspace: str) -> str | None:
    """Return brainstorm.md contents, or None."""
    path = _dir(workspace) / _BRAINSTORM
    if path.exists():
        return path.read_text(encoding="utf-8")
    return None


def load_recent_activity(workspace: str, limit: int = 5) -> list[dict[str, str]]:
    """Return the most recent conversation entries from activity.md."""
    path = _dir(workspace) / _ACTIVITY
    if not path.exists():
        return []

    lines = path.read_text(encoding="utf-8").splitlines()
    entries: list[dict[str, str]] = []
    current_date = ""
    current: dict[str, str] | None = None

    for line in lines:
        if line.startswith("## "):
            current_date = line[3:].strip()
            continue
        if line.startswith("### "):
            if current:
                entries.append(current)
            current = {"date": current_date, "time": line[4:].strip(), "user": "", "assistant": ""}
            continue
        if current is None:
            continue
        if line.startswith("**You:** "):
            current["user"] = line[len("**You:** "):].strip()
        elif line.startswith("**CodeMitra:** "):
            current["assistant"] = line[len("**CodeMitra:** "):].strip()

    if current:
        entries.append(current)

    return entries[-limit:]


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
    step_lines = [i for i, l in enumerate(lines) if l.startswith("- [ ]") or l.startswith("- [x]")]
    if 0 <= step_index < len(step_lines):
        i = step_lines[step_index]
        lines[i] = lines[i].replace("- [ ]", "- [x]", 1)
    path.write_text("\n".join(lines), encoding="utf-8")


def record_last_change_set(workspace: str, change_set: dict) -> None:
    """Persist the latest undoable change set for this workspace."""
    path = _dir(workspace) / _LAST_CHANGE
    payload = {
        "recorded_at": datetime.now().isoformat(timespec="seconds"),
        **change_set,
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def append_brainstorm_entry(workspace: str, prompt: str, response: str) -> pathlib.Path:
    """Append one brainstorm exchange to brainstorm.md."""
    path = _dir(workspace) / _BRAINSTORM
    now = datetime.now()
    stamp = now.strftime("%Y-%m-%d %H:%M")
    if not path.exists():
        header = textwrap.dedent("""\
            ---
            title: Brainstorm Notes
            tags: [codemitra, brainstorm, notes]
            ---

            # Brainstorm Notes

            > Saved idea exploration and planning notes from CodeMitra.
        """)
        path.write_text(header, encoding="utf-8")

    entry = (
        f"\n\n## {stamp}\n\n"
        f"**Prompt:** {prompt.strip()}\n\n"
        f"**CodeMitra:**\n\n{response.strip()}\n"
    )
    existing = path.read_text(encoding="utf-8")
    path.write_text(existing + entry, encoding="utf-8")
    return path


def load_last_change_set(workspace: str) -> dict | None:
    """Load the latest persisted change set, if any."""
    path = _dir(workspace) / _LAST_CHANGE
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def clear_last_change_set(workspace: str) -> None:
    """Remove the persisted change set after a successful undo."""
    path = _dir(workspace) / _LAST_CHANGE
    if path.exists():
        path.unlink()


def load_session_metadata(workspace: str) -> dict | None:
    """Load persisted session metadata for this workspace."""
    path = _dir(workspace) / _SESSION
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def save_session_metadata(workspace: str, metadata: dict) -> pathlib.Path:
    """Persist session metadata for this workspace."""
    path = _dir(workspace) / _SESSION
    payload = {
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        **metadata,
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def record_hibernation(workspace: str, summary: str, *, reason: str = "low-memory recovery") -> None:
    """Persist a lightweight recovery checkpoint into workspace memory files."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    append_activity(workspace, f"/hibernate ({reason})", summary)
    update_context(workspace, f"Hibernated at {now}: {reason}")

    plan_path = _dir(workspace) / _PLAN
    if plan_path.exists():
        text = plan_path.read_text(encoding="utf-8")
        updated = _replace_field(text, "updated", now)
        plan_path.write_text(updated, encoding="utf-8")


def ensure_session_metadata(workspace: str, *, default_name: str | None = None) -> dict:
    """Ensure a session metadata file exists and return its content."""
    existing = load_session_metadata(workspace)
    if existing:
        return existing

    root = pathlib.Path(workspace).resolve()
    metadata = {
        "name": default_name or root.name,
        "workspace": str(root),
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    save_session_metadata(workspace, metadata)
    return load_session_metadata(workspace) or metadata


def is_shell_command_trusted(workspace: str, cwd: str, command_name: str) -> bool:
    """Return True when a shell command is trusted for a specific directory."""
    metadata = ensure_session_metadata(workspace)
    trusted = metadata.get("shell_trust", {})
    commands = trusted.get(str(pathlib.Path(cwd).resolve()), [])
    return command_name in commands


def trust_shell_command(workspace: str, cwd: str, command_name: str) -> dict:
    """Persist trust for a shell command within a specific directory."""
    metadata = ensure_session_metadata(workspace)
    trusted = dict(metadata.get("shell_trust", {}))
    scope = str(pathlib.Path(cwd).resolve())
    commands = list(trusted.get(scope, []))
    if command_name not in commands:
        commands.append(command_name)
    trusted[scope] = sorted(commands)
    metadata["shell_trust"] = trusted
    save_session_metadata(workspace, metadata)
    return load_session_metadata(workspace) or metadata


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
    | `brainstorm.md` | Saved brainstorming and ideation notes |

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

    brainstorm_path = d / _BRAINSTORM
    if not brainstorm_path.exists():
        brainstorm_path.write_text(
            textwrap.dedent("""\
                ---
                title: Brainstorm Notes
                tags: [codemitra, brainstorm, notes]
                ---

                # Brainstorm Notes

                > Use `/brainstorm <topic>` to save idea exploration here.
            """),
            encoding="utf-8",
        )
        created.append(str(brainstorm_path.relative_to(pathlib.Path(workspace).resolve())))

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
