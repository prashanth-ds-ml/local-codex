# CodeMitra

> A local, offline AI coding assistant powered by [Ollama](https://ollama.com). No API keys. No cloud. No data leaves your machine.

---

## What it is

CodeMitra is a CLI tool that puts an AI coding assistant on your machine. It can chat about code, scaffold projects, create files and virtual environments, and install packages — all running locally via open-source models.

It is built with the same ideas behind Claude Code and GitHub Copilot, but entirely self-hosted.

---

## Features

- **Rich terminal UI** — ASCII avatar, styled panels, structured agent output
- **Chat** — powered by `qwen2.5-coder:7b`, optimised for code
- **Brainstorm loop** — `/plan` asks clarifying questions before generating a plan (ask before acting, not guess)
- **Planner agent** — breaks large goals into ordered steps, routes each step to the right agent
- **Filesystem agent** — creates folders, files, `.venv`, installs packages (10 tools)
- **Shell agent** — runs commands, captures output, streams results back to the LLM
- **Code reader agent** — reads and understands codebases (5 read-only tools)
- **Memory vault** — `.codemitra/` folder with session log, project context, and active plan
- **Dual-model routing** — chat LLM detects intent and delegates to the right agent
- **Permission guard** — workspace sandboxing + command whitelist

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
│       └── response.py    # ToolResult, AgentResponse, Rich renderer
├── misc/
│   └── ascii.py         # ASCII art generator for the banner
├── docs/                # Obsidian documentation vault
└── pyproject.toml
```

---

## Documentation

Full docs live in [`docs/`](docs/Home.md).

---

## Roadmap

See [`docs/Roadmap.md`](docs/Roadmap.md) for the full phase-by-phase build plan.

| Phase | Description | Status |
|---|---|---|
| 1–4 | Foundation, chat, filesystem agent, routing | ✅ Done |
| 5 | Code reader agent | ✅ Done |
| 6 | Shell agent | ✅ Done |
| 7 | Planner agent + brainstorm loop | ✅ Done |
| 8 | Memory vault | ✅ Done |
| 9 | Diff preview before writes | 🔲 Next |
| 10 | Test loop (`/fix` + pytest auto-retry) | 🔲 Planned |
| 11 | `/explain` and `/fix` slash commands | 🔲 Planned |
| 12 | Project auto-detect on startup | 🔲 Planned |

---

## Tech stack

- **LLM runtime** — Ollama
- **LLM framework** — LangChain (`langchain-ollama`, `langchain-core`)
- **Terminal UI** — Rich, prompt-toolkit
- **Language** — Python 3.11+
