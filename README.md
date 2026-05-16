# CodeMitra

> A local, offline AI coding assistant powered by [Ollama](https://ollama.com). No API keys. No cloud. No data leaves your machine.

---

## What it is

CodeMitra is a CLI tool that puts an AI coding assistant on your machine. It can chat about code, scaffold projects, create files and virtual environments, and install packages — all running locally via open-source models.

It is built with the same ideas behind Claude Code and GitHub Copilot, but entirely self-hosted.

---

## Features

- **Rich terminal UI** — clean startup screen, structured panels, persistent session toolbar
- **Chat-first UX** — starts conversationally, then routes into tools and agents when the request needs it
- **Brainstorm loop** — `/plan` asks clarifying questions before generating a plan (ask before acting, not guess)
- **Planner agent** — breaks large goals into ordered steps, routes each step to the right agent
- **Filesystem agent** — creates folders, files, `.venv`, installs packages (10 tools)
- **Shell agent** — runs commands, captures output, streams results back to the LLM, and can launch background tasks
- **Code reader agent** — reads and understands codebases (5 read-only tools)
- **Web agent** — native web search and page-reading with `/search` and `/open-url`
- **Memory vault** — `.codemitra/` folder with session log, project context, and active plan
- **Operator controls** — `/status`, `/context`, `/permissions`, `/model`, `/diff`, `/review`, `/fix`, `/resume`, `/hibernate`, `/tasks`
- **CodeMitra skills** — workspace skill discovery via `skills/*/SKILL.md`, plus `/skills` and `/skills show <name>` to inspect the active pack
- **Terminal operating surface** — bottom toolbar with mode, model, cwd, context load, and current task
- **Composer ergonomics** — `Ctrl+G` opens the current prompt in your editor for longer inputs
- **Permission guard** — workspace sandboxing, mode-based approvals, configurable roots and blocked tools
- **Startup auto-detect** — derives a lightweight project brief from the workspace and injects it at startup

## Current baseline

- **Validated product baseline** — 337 passing tests
- **Shipped workflow coverage** — bootstrap, understand, session lifecycle, plan lifecycle, safe edit, fix loop, research, safety/approval, background task UX
- **Operator decisions so far** — plan first for substantial work, diff before risky edits, explicit modes over hidden behavior, visible task state in the terminal, background shell work tracked as first-class tasks
- **Next product priorities** — LSP-backed diagnostics, MCP-style extensibility, deeper git workflow support, and better `/compact` UX

---

## Quick start

### 1. Install Ollama and pull models

```bash
ollama pull qwen2.5-coder:7b
ollama pull qwen3.5:latest
```

### 2. Clone and install

```bash
git clone https://github.com/prashanth-ds-ml/local-codex
cd local-codex
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS / Linux
pip install -e .
```

### 3. Run

```bash
codemitra
```

---

## Usage

```
codemitra> hi
codemitra> create a FastAPI project called myapi with a src/ folder and install fastapi uvicorn
codemitra> /run --background python -m http.server
codemitra> /tasks
codemitra> search the web for FastAPI background tasks
codemitra> /permissions
codemitra> /hibernate
codemitra> exit
```

---

## Project structure

```
local-codex/
├── app/
│   ├── main.py          # CLI entry point and chat REPL
│   ├── llm.py           # Model definitions (chat + agent)
│   ├── prompts.py       # System prompts and routing rules
│   ├── memory.py        # .codemitra/ vault (context, plan, activity log)
│   └── agents/
│       ├── brainstorm.py  # Clarifying Q&A loop before /plan
│       ├── filesystem.py  # 10 tools + permission guard + agent loop
│       ├── shell.py       # Command execution + whitelist + streaming
│       ├── reader.py      # 5 read-only tools for codebase understanding
│       ├── planner.py     # Step-by-step plan + per-step routing
│       ├── web.py         # Web search and page-reading helper
│       └── response.py    # ToolResult, AgentResponse, Rich renderer
├── misc/
│   └── ascii.py         # ASCII art generator for the banner
├── docs/                # Obsidian documentation vault
└── pyproject.toml
```

---

## Documentation

Full docs live in [`docs/`](docs/Home.md).

Key product-direction docs:

- [`docs/Product Blueprint.md`](docs/Product%20Blueprint.md) - feature baseline and target UX
- [`docs/Roadmap.md`](docs/Roadmap.md) - implementation phases
- [`docs/Testing Strategy.md`](docs/Testing%20Strategy.md) - regression layers, workflows, and transcript coverage
- [`docs/Vision.md`](docs/Vision.md) - why CodeMitra exists and what gap it closes

---

## Roadmap

See [`docs/Roadmap.md`](docs/Roadmap.md) for the full phase-by-phase build plan.

| Phase | Description | Status |
|---|---|---|
| 1–4 | Foundation, chat, filesystem agent, routing | ✅ Done |
| 5 | Code reader agent | ✅ Done |
| 6 | Shell agent | ✅ Done |
| 7 | Planner agent | ✅ Done |
| 8 | Memory vault | ✅ Done |
| 9 | Brainstorm loop | ✅ Done |
| 10 | Trust layer: diff preview + approvals | ✅ Done |
| 11 | Repair loop + operator commands | ✅ Done |
| 12 | Session UX | ✅ Mostly done |
| 13 | Project auto-detect + code intelligence | ✅ Started |
| 14 | Extensibility + policy controls | ✅ Started |
| 15 | Git-aware workflows | 🔲 Planned |

---

## Tech stack

- **LLM runtime** — Ollama
- **LLM framework** — LangChain (`langchain-ollama`, `langchain-core`)
- **Terminal UI** — Rich, prompt-toolkit
- **Language** — Python 3.11+
