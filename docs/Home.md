---
title: CodeMitra
tags: [codemitra, home, index]
aliases: [Home, Index]
---

# CodeMitra

> Local AI coding assistant · Powered by Ollama · 100% offline

---

## Navigation

| Doc | What's inside |
|---|---|
| [[Setup]] | Install, configure, and run |
| [[Architecture]] | How the system is designed |
| [[Roadmap]] | Phase-by-phase build plan |
| [[Vision]] | Why CodeMitra exists — the Ollama capability gap |
| [[Tech Stack]] | Every dependency, layer by layer |
| [[Multi-Agent System]] | Full agent roster and how they connect |
| [[agents/Filesystem Agent]] | The first agent — files, venvs, packages |
| [[reference/Ollama Models]] | Which models support tool calling and which don't |
| [[reference/Tools]] | All 10 tools reference |
| [[reference/Models]] | Model selection and why two models |
| [[reference/Permissions]] | Workspace sandboxing and command whitelist |

---

## What CodeMitra does

```
You type naturally → Chat LLM decides what to do
                           │
              ┌────────────┴────────────┐
              │                         │
         Chat reply              Filesystem agent
    (explain, debug,         (create folders, files,
      generate code)          venv, install packages)
```

---

## Current state

- [x] CLI with Rich banner
- [x] Chat loop (`qwen2.5-coder:7b`)
- [x] Filesystem agent with 10 tools + permission guard
- [x] Shell agent — commands, whitelist, streaming output
- [x] Code reader agent — 5 read-only tools, path sandbox
- [x] Planner agent — multi-step plans routed to sub-agents
- [x] Brainstorm loop — clarifying Q&A before `/plan`
- [x] Memory vault — `.codemitra/` with context, plan, activity log
- [ ] Diff preview before bulk file writes
- [ ] Test loop (`/fix` + pytest auto-retry)
- [ ] `/explain` and `/fix` slash command shortcuts
- [ ] Project auto-detect on startup

> [!tip] Start here
> If you're setting up for the first time, go to [[Setup]].
