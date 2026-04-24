---
title: Tech Stack
tags: [tech-stack, langchain, python, ollama, architecture]
aliases: [Stack, Dependencies, Technology]
---

# Tech Stack

## Overview

```
┌─────────────────────────────────────────────────────────┐
│                      CodeMitra                          │
│                                                         │
│   ┌──────────┐    ┌──────────┐    ┌──────────────────┐  │
│   │  Rich    │    │ prompt-  │    │   pyproject.toml  │  │
│   │ (UI)     │    │ toolkit  │    │   (packaging)     │  │
│   └──────────┘    └──────────┘    └──────────────────┘  │
│                                                         │
│   ┌─────────────────────────────────────────────────┐   │
│   │               LangChain                         │   │
│   │  langchain-core   langchain-ollama              │   │
│   │  (messages, tools, agent loop abstraction)      │   │
│   └─────────────────────────────────────────────────┘   │
│                                                         │
│   ┌─────────────────────────────────────────────────┐   │
│   │                  Ollama                         │   │
│   │  Local LLM runtime — serves models via HTTP     │   │
│   └─────────────────────────────────────────────────┘   │
│                                                         │
│   ┌──────────┐    ┌──────────┐    ┌──────────────────┐  │
│   │ Pillow   │    │  NumPy   │    │   subprocess /   │  │
│   │ (banner) │    │ (banner) │    │   pathlib / os   │  │
│   └──────────┘    └──────────┘    └──────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

---

## Layer by layer

### 1. Model runtime — Ollama

Ollama is the local server that downloads, stores, and serves open-source LLMs. It exposes an HTTP API that LangChain talks to.

```bash
ollama serve          # starts the server (auto-starts on most systems)
ollama pull model     # downloads a model
ollama list           # shows installed models
```

**Why Ollama?** It is the simplest way to run local LLMs on any OS, with GPU acceleration support and a growing model library.

---

### 2. LLM framework — LangChain

LangChain is the bridge between Python code and the Ollama models. It provides:

#### `langchain-ollama` — Model integration

```python
from langchain_ollama import ChatOllama

llm = ChatOllama(model="qwen3.5:latest", temperature=0)
response = llm.invoke("hello")
```

#### `langchain-core` — Message types

LangChain defines structured message types that maintain conversation context and enable tool calling:

| Message type | When used |
|---|---|
| `SystemMessage` | Sets the agent's behaviour and constraints |
| `HumanMessage` | The user's input |
| `AIMessage` | The model's response (may contain tool_calls) |
| `ToolMessage` | The result of a tool execution, fed back to the model |

```python
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
```

#### `langchain-core` — Tool binding

```python
from langchain_core.tools import tool

@tool
def create_folder(path: str) -> str:
    "Create a directory at the given path."
    import pathlib
    pathlib.Path(path).mkdir(parents=True, exist_ok=True)
    return f"✓ Created folder: {path}"

llm_with_tools = llm.bind_tools([create_folder])
response = llm_with_tools.invoke(messages)
# response.tool_calls contains structured calls if the model supports it
```

**Why LangChain?** It abstracts the differences between model providers, standardises message formats, and handles tool schema generation automatically from Python function signatures and docstrings.

---

### 3. Agent loop — Pure Python

The agent loop is hand-written in `app/agents/filesystem.py`. It does not use LangChain's built-in `AgentExecutor` or LangGraph — keeping it simple and fully transparent:

```python
def run(llm, user_request: str) -> AgentResponse:
    messages = [SystemMessage(...), HumanMessage(user_request)]

    while True:
        response = llm.bind_tools(tools).invoke(messages)
        messages.append(response)

        if not response.tool_calls:
            return AgentResponse(summary=response.content, steps=steps)

        for tc in response.tool_calls:
            result = tool_map[tc["name"]].invoke(tc["args"])
            steps.append(ToolResult(tc["name"], tc["args"], result))
            messages.append(ToolMessage(content=result, tool_call_id=tc["id"]))
```

**Why hand-written?** Full visibility. No magic. Easy to extend with permission checks, structured responses, and custom routing.

---

### 4. Terminal UI — Rich + prompt-toolkit

| Library | Role |
|---|---|
| `rich` | Panels, tables, rules, coloured text, status spinners |
| `prompt-toolkit` | Input prompt with in-memory history (arrow keys work) |

```python
from rich.console import Console
from rich.panel import Panel
from prompt_toolkit import PromptSession

console = Console()
session = PromptSession(history=InMemoryHistory())

user_input = session.prompt("codemitra> ")
console.print(Panel(response, title="CodeMitra", border_style="cyan"))
```

---

### 5. Image processing — Pillow + NumPy

Used only for the ASCII art banner. The monkey image is converted to grayscale pixels and mapped to block characters.

---

### 6. Packaging — pyproject.toml

```toml
[project.scripts]
codemitra = "app.main:main"
```

Running `pip install -e .` registers `codemitra` as a system command that activates with the venv.

---

## Full dependency list

```toml
dependencies = [
    "rich",               # terminal UI
    "prompt-toolkit",     # input with history
    "langchain-ollama",   # Ollama ↔ LangChain bridge
    "langchain-core",     # messages, tools, types
    "python-dotenv",      # .env config loading
    "Pillow",             # image → ASCII art
    "numpy",              # pixel array operations
]
```

---

## How Model → LLM → Agent connects

```
Ollama (runtime)
    └── serves qwen3.5:latest on localhost:11434
            │
            ▼
ChatOllama (LangChain wrapper)
    └── get_agent_llm() → ChatOllama(model="qwen3.5:latest")
            │
            ▼
bind_tools([create_folder, create_file, ...])
    └── sends tool schemas to model alongside the prompt
            │
            ▼
Agent loop (filesystem.run())
    ├── invokes the LLM with messages
    ├── reads response.tool_calls
    ├── executes each tool through the PermissionGuard
    ├── appends ToolMessage results back to messages
    └── repeats until no more tool calls → returns AgentResponse
```

The **model** is the brain. The **LLM wrapper** is the communication layer. The **agent loop** is the execution engine that keeps things going until the job is done.
