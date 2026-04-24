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
- **Filesystem agent** — creates folders, files, `.venv`, installs packages
- **Dual-model routing** — chat LLM routes tasks to agent LLM (`qwen3.5:latest`) which actually supports structured tool calling
- **Permission guard** — workspace sandboxing + command whitelist
- **10 tools** — create, read, move, delete, venv, install, shell

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
│   ├── main.py          # CLI entry point and chat loop
│   ├── llm.py           # Model definitions (chat + agent)
│   ├── prompts.py       # System prompts
│   └── agents/
│       ├── filesystem.py  # 10 tools + permission guard + agent loop
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

See [[Roadmap]] for the full phase-by-phase build plan.

| Phase | Description | Status |
|---|---|---|
| 1–4 | Foundation, chat, filesystem agent, routing | ✅ Done |
| 5 | Code reader agent | ⬜ Next |
| 6 | Shell agent | ⬜ Planned |
| 7 | Planner / orchestrator | ⬜ Planned |
| 8 | Memory | ⬜ Planned |

---

## Tech stack

- **LLM runtime** — Ollama
- **LLM framework** — LangChain (`langchain-ollama`, `langchain-core`)
- **Terminal UI** — Rich, prompt-toolkit
- **Language** — Python 3.11+
