---
title: Models
tags: [models, ollama, llm, configuration]
aliases: [Model Guide, LLM Setup]
---

# Models

CodeMitra uses two models simultaneously — one for chat, one for agent tool use.

---

## Why two models?

Not all local models support **structured tool calling** — the ability to return a properly formed function call object (not just text describing what to call). CodeMitra's agents depend on this to work reliably.

`qwen2.5-coder:7b` is excellent at code tasks but outputs tool calls as plain text. `qwen3.5:latest` supports structured tool calling properly.

| Model | Chat / Code | Structured tool calls |
|---|---|---|
| `qwen2.5-coder:7b` | ✅ Excellent | ❌ Text only |
| `qwen3.5:4b` | ✓ Good | ✅ Yes |
| `qwen3.5:latest` | ✓ Good | ✅ Yes |
| `gemma4:latest` | ✓ Good | ✅ Yes |
| `deepseek-r1:8b` | ✓ Good | ❌ Error 400 |

---

## Current configuration

Defined in `app/llm.py`:

```python
def get_chat_llm() -> ChatOllama:
    """Chat and code — qwen2.5-coder specialised for code generation."""
    return ChatOllama(model="qwen2.5-coder:7b", temperature=0.2)


def get_agent_llm() -> ChatOllama:
    """Agent and tool-use — qwen3.5 with reliable structured tool calling."""
    return ChatOllama(model="qwen3.5:latest", temperature=0)
```

**Chat LLM** (`qwen2.5-coder:7b`, temp 0.2):
- Handles all conversation
- Code generation, explanation, debugging
- Routes filesystem tasks to the agent via the `setup_project` tool

**Agent LLM** (`qwen3.5:latest`, temp 0):
- Only activated for agent tasks
- Executes tool-calling loops
- Temperature 0 for deterministic, reliable tool use

---

## How to change models

Edit `app/llm.py`. Any Ollama model can be used.

> [!warning] Agent model requirement
> The agent model **must** support structured tool calling. Test before switching:
> ```python
> from langchain_ollama import ChatOllama
> from langchain_core.tools import tool
>
> @tool
> def add(a: int, b: int) -> int:
>     "Add two numbers."
>     return a + b
>
> llm = ChatOllama(model="your-model").bind_tools([add])
> resp = llm.invoke("what is 3 + 5?")
> print("structured?" , bool(resp.tool_calls))
> ```

---

## Pulling models

```bash
ollama pull qwen2.5-coder:7b
ollama pull qwen3.5:latest

# Smaller alternative for the agent (3.4 GB)
ollama pull qwen3.5:4b
```

---

## Model size reference

| Model | Size | Role |
|---|---|---|
| `qwen2.5-coder:7b` | 4.7 GB | Chat |
| `qwen3.5:4b` | 3.4 GB | Agent (lighter) |
| `qwen3.5:latest` | 6.6 GB | Agent (default) |
| `gemma4:latest` | 9.6 GB | Agent (alternative) |
