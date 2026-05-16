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
| [[Claude Code Reference]] | Claude-style runtime and platform ideas captured as a reference |
| [[Roadmap]] | Phase-by-phase build plan |
| [[Vision]] | Why CodeMitra exists — the Ollama capability gap |
| [[Product Blueprint]] | Feature baseline, target UX, and next product priorities |
| [[Claude Code Comparison]] | Detailed gap analysis against the captured Claude Code baseline |
| [[Testing Strategy]] | Test pyramid, workflow suite, and transcript regression model |
| [[Tech Stack]] | Every dependency, layer by layer |
| [[Multi-Agent System]] | Full agent roster and how they connect |
| [[agents/Filesystem Agent]] | The first agent — files, venvs, packages |
| [[reference/Ollama Models]] | Which models support tool calling and which don't |
| [[reference/Tools]] | All 10 tools reference |
| [[reference/Models]] | Model selection and why two models |
| [[reference/Permissions]] | Workspace sandboxing and command whitelist |

---

## How to use this docs set

| If you want to know... | Start here |
|---|---|
| why CodeMitra exists | [[Vision]] |
| how it works today | [[Architecture]] |
| how agents are split up | [[Multi-Agent System]] |
| where the product should go next | [[Roadmap]] |
| the target UX and behavior model | [[Product Blueprint]] |
| the Claude-specific benchmark and gaps | [[Claude Code Reference]] → [[Claude Code Comparison]] |
| how the project is tested | [[Testing Strategy]] |

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

- Chat-first CLI with natural routing into filesystem, shell, reader, planner, web, review, and explain flows
- Trust-oriented workflow with planning, approval modes, diff preview, review, and undo
- Session surfaces including status, context, permissions, resume, compact, hibernate, and background task tracking
- Local project memory under `.codemitra/` plus project rules and workspace skill discovery
- Product-level workflow regression coverage across the core operator journeys

For the detailed breakdown of current capabilities, use [[Architecture]], [[Multi-Agent System]], and [[Testing Strategy]] instead of this landing page.

## Decisions so far

- CodeMitra stays **local-first and offline by default**
- The product favors **plan-first and approval-first UX** over hidden automation
- Session behavior is always explicit through **modes**: `read-only`, `plan`, `approve`, `auto`
- Risky edits should be **diff-first** and reversible through `/undo`
- Long-running work should stay visible with **toolbar + status + task surfaces**
- Testing should protect **operator workflows**, not just helpers

## Current baseline

- **Validated test baseline:** 337 passing tests
- **Workflow packs completed:** bootstrap, understand, session lifecycle, navigation, plan lifecycle, safe edit, fix, research, safety/approval, background task UX

## Next steps

The authoritative next-step list lives in [[Roadmap]].

For behavior targets, use [[Product Blueprint]].

For Claude-specific benchmark context and gaps, use [[Claude Code Reference]] and [[Claude Code Comparison]].

> [!tip] Start here
> If you're setting up for the first time, go to [[Setup]].
