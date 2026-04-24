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
| [[agents/Filesystem Agent]] | The first agent — files, venvs, packages |
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
- [x] Filesystem agent (`qwen3.5:latest`) with 10 tools
- [x] Permission guard
- [x] Structured response templates
- [ ] Code reader agent
- [ ] Shell agent
- [ ] Planner agent
- [ ] Memory / persistence

> [!tip] Start here
> If you're setting up for the first time, go to [[Setup]].
