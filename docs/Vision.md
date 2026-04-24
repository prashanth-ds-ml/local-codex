---
title: Vision
tags: [vision, motivation, why, gap]
aliases: [Why CodeMitra, Motivation]
---

# Vision — Why CodeMitra Exists

## The problem

Tools like Claude Code, GitHub Copilot, and Cursor work seamlessly because they are tightly integrated with their own proprietary models. The models are specifically fine-tuned for tool calling, code understanding, and multi-step reasoning. The tool layer and the model layer are designed together.

When you try to replicate that experience locally with Ollama, you hit a wall immediately:

- Most open-source models at 7B–8B parameters do not support **structured tool calling**
- Models that do support it often hallucinate tool names, wrong arguments, or output the call as plain text instead of a proper function call object
- There is no routing layer — you have one model doing everything, and it is not great at any one thing
- There is no agent loop — the model gives you a response, and that is the end of the interaction
- There is no memory — every conversation starts from zero

The result is a model that can chat about code but cannot act on it. It tells you what to do instead of doing it.

---

## The insight

Claude Code works because it is not just a model. It is a **system** built on top of a model:

```
Claude Code = Model + Routing + Multiple Agents + Tools + Memory + Loop
```

Each agent has a specific job. Each tool has a specific function. The model only decides — it never executes. Execution happens in Python, safely, with guardrails.

That system can be built locally with Ollama. It just requires building the infrastructure that the proprietary tools bundle with their models.

---

## What CodeMitra is building

A local, offline, open-source equivalent of Claude Code — not by finding one perfect model, but by building the **system** that makes multiple imperfect models work together.

```
CodeMitra = Ollama Models + LangChain + Multi-Agent Routing + Tools + Memory
```

The key idea: **use the right model for the right job**.

- A code-specialist model handles chat and code generation
- A tool-calling-capable model handles agent execution
- A planner model (or the same model with a different prompt) handles task decomposition
- The system routes between them automatically

---

## The gap we are closing

| Capability | Claude Code | Ollama alone | CodeMitra goal |
|---|---|---|---|
| Chat about code | ✅ | ✅ | ✅ |
| Structured tool calling | ✅ | ⚠️ model-dependent | ✅ with right model |
| Create files / scaffold | ✅ | ❌ | ✅ |
| Read and understand existing code | ✅ | ❌ | 🔨 building |
| Run shell commands and react | ✅ | ❌ | 🔨 building |
| Multi-step planning | ✅ | ❌ | 🔨 building |
| Ask clarifying questions | ✅ | ❌ | 🔨 building |
| Memory across sessions | ✅ | ❌ | 🔨 building |
| Works on any project | ✅ | ❌ | 🔨 building |
| 100% offline | ❌ | ✅ | ✅ |
| No API costs | ❌ | ✅ | ✅ |
| Your data stays local | ❌ | ✅ | ✅ |

---

## The long-term goal

CodeMitra should be able to:

1. Open a new or existing project
2. Read and understand the codebase
3. Have a conversation with the developer about what needs to be built
4. Ask clarifying questions about anything ambiguous
5. Build a phased implementation plan
6. Execute the plan using agents — writing code, creating files, running tests
7. Review its own output and iterate
8. Remember context across sessions so it picks up where it left off

All of this, running entirely on your machine, with no external API calls.
