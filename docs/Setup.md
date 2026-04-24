---
title: Setup
tags: [setup, install, quickstart]
aliases: [Installation, Getting Started]
---

# Setup

## Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | 3.11+ | `python --version` |
| Ollama | Latest | [ollama.com](https://ollama.com) |
| Git | Any | For cloning |

---

## 1. Install Ollama

Download from [ollama.com](https://ollama.com) and install. Then pull the two models CodeMitra uses:

```bash
ollama pull qwen2.5-coder:7b   # chat + code  (4.7 GB)
ollama pull qwen3.5:latest      # agent tools  (6.6 GB)
```

> [!info] Why two models?
> See [[reference/Models]] for the full explanation. Short version: `qwen2.5-coder` is better at code but doesn't support structured tool calling. `qwen3.5` does.

---

## 2. Clone the repo

```bash
git clone https://github.com/prashanth-ds-ml/local-codex
cd local-codex
```

---

## 3. Create virtual environment and install

```bash
# Windows
python -m venv .venv
.venv\Scripts\activate
pip install -e .

# macOS / Linux
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

---

## 4. Run

```bash
codemitra
```

You should see the banner with the ASCII avatar and taglines, then the `codemitra>` prompt.

---

## Verify it works

```
codemitra> hi
codemitra> create a folder called test-project with a .venv and install requests
codemitra> exit
```

---

## Changing models

Edit `app/llm.py`:

```python
def get_chat_llm():
    return ChatOllama(model="qwen2.5-coder:7b", temperature=0.2)

def get_agent_llm():
    return ChatOllama(model="qwen3.5:latest", temperature=0)
```

> [!warning] Agent model requirement
> The agent LLM **must** support structured tool calling. See [[reference/Models]] for which local models work.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `codemitra` not found | Make sure the venv is activated and you ran `pip install -e .` |
| Ollama connection error | Run `ollama serve` in a separate terminal |
| Model not found | Run `ollama pull <model-name>` |
| Unicode errors in terminal | Upgrade to Windows Terminal or PowerShell 7+ |
