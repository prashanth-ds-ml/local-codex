---
title: Ollama Models
tags: [models, ollama, tool-calling, reference]
aliases: [Model Capabilities, Which Model to Use]
---

# Ollama Models — Tool Calling Capability Guide

Not all Ollama models support structured tool calling. This is the single most important factor when choosing a model for an agent.

---

## What structured tool calling means

When you bind tools to an LLM using LangChain's `bind_tools()`, the model needs to return a properly structured tool call object:

```python
response.tool_calls = [
    {"name": "create_folder", "args": {"path": "myapi/src"}, "id": "abc123"}
]
```

If the model does NOT support this, it outputs the call as plain text in `response.content` instead:

```
{"name": "create_folder", "arguments": {"path": "myapi/src"}}
```

When that happens, `response.tool_calls` is empty and the agent loop cannot execute the tool. The model just describes what it would do instead of doing it.

---

## How to test any model

```python
from langchain_ollama import ChatOllama
from langchain_core.tools import tool

@tool
def add(a: int, b: int) -> int:
    "Add two numbers."
    return a + b

llm = ChatOllama(model="your-model-name", temperature=0)
resp = llm.bind_tools([add]).invoke("what is 3 + 5?")

print("tool_calls:", resp.tool_calls)
print("content:   ", resp.content)

if resp.tool_calls:
    print("RESULT: structured tool calling WORKS")
else:
    print("RESULT: model does NOT support structured tool calling")
```

---

## Tested models

### ✅ Supports structured tool calling

| Model | Size | Notes |
|---|---|---|
| `qwen3.5:4b` | 3.4 GB | Best balance — small, fast, reliable tool calling |
| `qwen3.5:latest` | 6.6 GB | **Default agent model in CodeMitra** |
| `gemma4:latest` | 9.6 GB | Works but large |
| `llama3.1:8b` | 4.7 GB | Meta's model, reliable tool calling |
| `llama3.2:3b` | 2.0 GB | Smaller Llama, supports tools |
| `mistral:7b` | 4.1 GB | Good tool calling support |

### ❌ Does NOT support structured tool calling

| Model | Size | Behaviour |
|---|---|---|
| `qwen2.5-coder:7b` | 4.7 GB | Outputs tool calls as plain text |
| `deepseek-r1:8b` | 5.2 GB | Returns HTTP 400 — explicitly rejects tool binding |
| `codellama:7b` | 3.8 GB | Not designed for tool calling |
| `phi3:mini` | 2.3 GB | Does not support structured output |

> [!note] This list will grow
> Run the test above on any new model you pull. The landscape changes with every Ollama release.

---

## How CodeMitra handles the gap

CodeMitra uses a **dual-model strategy**:

```
qwen2.5-coder:7b  ──  chat, code generation, explanation
        │
        │  (detects task requires action)
        │
        ▼
qwen3.5:latest    ──  agent execution, tool calling, structured output
```

The chat model handles conversation. When the user asks for something that requires action (creating files, running commands), the chat model triggers the agent model via the `setup_project` routing tool.

This means:
- You get the best code-generation quality from a code-specialist model
- You get reliable tool execution from a model that actually supports it
- Neither model has to do both jobs

---

## Recommended setup

**Minimum (3.4 GB agent model):**
```bash
ollama pull qwen2.5-coder:7b   # chat
ollama pull qwen3.5:4b          # agent
```

**Default CodeMitra setup (6.6 GB agent model):**
```bash
ollama pull qwen2.5-coder:7b   # chat
ollama pull qwen3.5:latest      # agent
```

**High quality (larger models, more VRAM required):**
```bash
ollama pull qwen2.5-coder:14b   # chat
ollama pull qwen3.5:latest       # agent
```

---

## Why this matters for a coding assistant

A coding assistant that cannot reliably call tools is just a chatbot. It can describe what to do but cannot do it. Structured tool calling is what separates a **conversational assistant** from an **autonomous agent** that actually modifies your filesystem, runs commands, and builds things.

See [[../Vision]] for the full context on why this gap exists and what CodeMitra is doing about it.
