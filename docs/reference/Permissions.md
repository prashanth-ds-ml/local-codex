---
title: Permissions
tags: [permissions, security, guard, configuration]
aliases: [Permission Guard, Security]
---

# Permissions

CodeMitra now has **two permission layers**:

1. the low-level `PermissionGuard` in `app/agents/filesystem.py`
2. the interactive session policy shown by `/permissions`

Together they keep the assistant predictable: what it can touch, when it asks, and which commands stay blocked.

---

## What it enforces

| Check | What it does |
|---|---|
| **Workspace** | All path arguments must resolve inside a configured root directory |
| **Tool allowlist** | Only tools in `allowed_tools` are bound to the agent LLM |
| **Command whitelist** | Only executables in `allowed_commands` can be run via `run_command` |
| **Session mode** | `read-only`, `plan`, `approve`, and `auto` change whether CodeMitra can inspect, plan, ask, or act |
| **Config policy** | `allowed_roots`, `disabled_tools`, and `disabled_commands` from `codemitra.toml` further narrow access |
| **Background task policy** | `/run --background` uses the same shell approval, mode, and command restrictions as foreground shell execution |
| **Skill scope** | `skill_dirs` are discovered only inside the workspace; `/skills show <name>` reads only discovered `SKILL.md` files |

---

## Default state

Out of the box, with no configuration:

```python
_guard = PermissionGuard()
# workspace      = None  (no path restriction)
# allowed_tools  = {create_folder, create_file, read_file,
#                   list_directory, create_venv, install_packages}
# allowed_commands = {python, python3, pip, pip3, git, npm, node, uvicorn}
```

**Destructive tools are off by default:**

| Tool | Default |
|---|---|
| `create_folder` | ✅ on |
| `create_file` | ✅ on |
| `read_file` | ✅ on |
| `list_directory` | ✅ on |
| `create_venv` | ✅ on |
| `install_packages` | ✅ on |
| `delete_file` | ❌ off |
| `delete_folder` | ❌ off |
| `move_file` | ❌ off |
| `run_command` | ❌ off |

---

## Runtime session policy

Use `/permissions` inside CodeMitra to see the current live policy:

- active mode
- current workspace and shell cwd
- additional allowed roots
- disabled file tools
- disabled shell commands
- trust behavior for repeated shell commands
- background task visibility and restrictions
- discovered workspace skill directories

### Mode behavior

| Mode | Behavior |
|---|---|
| `read-only` | Inspect only. No code-changing execution. |
| `plan` | Inspect and create plans, but do not execute edits or shell actions. |
| `approve` | Default coding mode. Ask before file changes and shell commands. |
| `auto` | Auto-approve in-workspace edits and shell actions allowed by policy. |

> [!tip]
> Use `/mode` to change the active session behavior and `/status` or `/permissions` to inspect it.

---

## Configuring the guard

Use `filesystem.configure()` at startup or before running a task:

```python
from app.agents import filesystem

# Lock agent to a specific project directory
filesystem.configure(workspace="C:/Users/prash/projects/myapi")

# Enable destructive tools within the workspace
filesystem.configure(
    workspace="C:/Users/prash/projects/myapi",
    allowed_tools=filesystem._DEFAULT_TOOLS | {"delete_file", "move_file"},
)

# Enable run_command with a custom command whitelist
filesystem.configure(
    workspace="C:/Users/prash/projects/myapi",
    allowed_tools=filesystem._DEFAULT_TOOLS | {"run_command"},
    allowed_commands={"python", "git", "npm"},
)
```

> [!tip] Reset to defaults
> Call `filesystem.configure()` with no arguments to restore the default guard.

For broader session policy, CodeMitra also reads `codemitra.toml`:

```toml
allowed_roots = ["extra"]
disabled_tools = ["delete_file"]
disabled_commands = ["python"]
instruction_files = ["AGENTS.md", ".codemitra/instructions.md"]
skill_dirs = ["skills", ".codemitra/skills"]
```

These settings are surfaced directly in `/permissions`. Instruction files and skill files are read only from inside the workspace. Project instructions are injected into the startup system prompt; skills inject only a compact index, and full `SKILL.md` bodies are shown or read on demand.

---

## How workspace checking works

Every path argument is resolved to an absolute path and checked with `Path.relative_to()`:

```python
def check_path(self, *paths: str) -> str | None:
    for p in paths:
        try:
            Path(p).resolve().relative_to(self.workspace)
        except ValueError:
            return f"✗ Permission denied: '{p}' is outside workspace"
    return None
```

If the check fails, the tool returns the error string immediately — no filesystem operation occurs.

---

## How command checking works

The `run_command` tool extracts the executable name from the command string and checks it against the whitelist:

```python
exe = Path(shlex.split(command)[0]).name
if exe not in self.allowed_commands:
    return f"✗ Permission denied: '{exe}' is not in the allowed commands list"
```

This means:
- `python -m venv .venv` → executable is `python` → ✅ allowed by default
- `rm -rf /` → executable is `rm` → ❌ blocked

---

## How tool filtering works

`filter_tools()` is called inside `run()` before the agent loop starts:

```python
active_tools = _guard.filter_tools(_ALL_TOOLS)
llm_with_tools = llm.bind_tools(active_tools)
```

The agent LLM only sees — and can only call — the tools that are currently permitted. A tool that isn't bound cannot be hallucinated into existence by the model.
