---
title: Permissions
tags: [permissions, security, guard, configuration]
aliases: [Permission Guard, Security]
---

# Permissions

The `PermissionGuard` class in `app/agents/filesystem.py` protects against the agent operating outside its intended scope — whether due to a bad prompt, a hallucinated path, or a prompt injection attempt.

---

## What it enforces

| Check | What it does |
|---|---|
| **Workspace** | All path arguments must resolve inside a configured root directory |
| **Tool allowlist** | Only tools in `allowed_tools` are bound to the agent LLM |
| **Command whitelist** | Only executables in `allowed_commands` can be run via `run_command` |

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
