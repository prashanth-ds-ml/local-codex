---
title: Claude Code Reference
tags: [reference, benchmark, claude, architecture]
aliases: [Claude Reference, Claude CLI Reference, Claude Code Deep Dive]
---

# Claude Code Reference

## Why this doc exists

This document captures the **useful architectural ideas** from the pasted Claude Code CLI deep-dive and saves them as a reusable reference for CodeMitra.

It is intentionally different from the other benchmark docs:

- [[Product Blueprint]] = multi-product behavior target
- [[Claude Code Comparison]] = CodeMitra vs Claude gap analysis
- **this doc** = Claude-style reference model in a source-style summary

---

## What this reference is good for

Use this doc when the question is:

- how does a Claude-style terminal coding assistant work under the hood?
- what platform layers sit below the chat UI?
- what pieces would CodeMitra need if it wanted Claude-like extensibility and control?

This is a **reference architecture**, not a product requirement checklist.

---

## 1. Core agentic loop

The reference describes a three-part loop:

1. **Gather context** — read files, search code, inspect system state
2. **Take action** — edit files, run commands, call tools, invoke APIs
3. **Verify results** — inspect output, rerun commands, validate the change

The key idea is that the harness is reactive:

- the model decides what it wants to do
- the runtime executes the requested tool
- the tool result returns to the model
- the loop continues until there are no more tool calls

That means the assistant is not just “a chatbot with commands.” It is a **tool-calling runtime with a conversational front end**.

---

## 2. Tool categories in the reference model

### File operations

The reference system distinguishes between several file behaviors:

- read
- exact edit
- full overwrite
- notebook-aware edit

The important lesson is not the exact tool names. The lesson is that the runtime treats file operations as **first-class structured actions**, not free-form shell work.

### Search and discovery

The reference includes:

- glob-style file search
- grep/ripgrep-style content search
- language-aware code intelligence via LSP

This is one of the most important differences between a generic assistant and a coding assistant.

### Execution

The reference separates:

- shell execution
- Windows-native PowerShell behavior
- background process monitoring

Execution is not just “run a command.” It includes:

- timeouts
- output limits
- current-directory rules
- background visibility

### Web

The reference distinguishes:

- search results
- page fetching / page reading

That separation matters because “search” and “open/read URL” are different operator actions.

### Orchestration

The reference also treats orchestration as tools:

- spawning subagents
- asking the user focused questions
- task tracking
- worktree entry/exit
- plan mode entry/exit
- deferred tool discovery

This is a major architectural point: **workflow control is part of the tool surface**.

---

## 3. Slash command surface

The pasted reference shows a broad slash-command layer covering:

- session flow
- configuration
- planning
- review
- scheduling
- memory
- custom agents
- skills

The useful takeaway is that slash commands are not just shortcuts. They are **operator controls** for managing the assistant as a live system.

Representative categories:

| Category | Examples from the reference |
|---|---|
| Session and workflow | `/resume`, `/branch`, `/continue`, `/context`, `/compact`, `/clear` |
| Configuration | `/init`, `/config`, `/model`, `/memory`, `/permissions` |
| Orchestration | `/agents`, `/plan`, `/batch` |
| Review and analysis | `/review`, `/security-review` |
| Scheduling | `/loop`, `/schedule` |

For CodeMitra, the important lesson is not command-count parity. The lesson is to keep an explicit **operator surface** for state, permissions, plans, and review.

---

## 4. Skills model

The reference describes skills as markdown-defined workflow units with metadata such as:

- name
- description
- tool allowances
- model override
- invocation behavior
- arguments
- context mode

This is more powerful than simple prompt snippets. In that model, skills are closer to **workflow modules**.

Important ideas from the reference:

- skills can be personal or project-scoped
- a skill can shape execution behavior, not just prompt text
- the system can preserve invoked skills across compaction

---

## 5. Hooks and events

One of the biggest architectural ideas in the pasted reference is the hooks system.

The reference exposes lifecycle events around:

- session start/end
- user prompt submission
- tool execution
- permission requests
- compaction
- file changes
- subagent lifecycle
- task lifecycle

Handlers can take different forms:

- command hooks
- HTTP hooks
- MCP tool hooks
- prompt hooks
- agent hooks

This matters because it turns the assistant into an **extensible governed runtime**, not just a fixed app.

---

## 6. Settings architecture

The reference uses hierarchical settings with precedence across scopes such as:

- managed settings
- CLI arguments
- local project overrides
- project settings
- user settings

Two important principles stand out:

1. **deny rules win**
2. settings are merged thoughtfully rather than treated as one flat config blob

This is the foundation for advanced permission rules, hooks, and external tool integrations.

---

## 7. MCP and deferred tool discovery

The pasted reference includes MCP support with:

- multiple transport types
- namespaced tools
- permission rules for MCP tools
- deferred schema loading through tool search

The key design lesson is that external integrations should not bloat every session up front. Deferred discovery keeps the base runtime lighter.

This is a classic platform-design move:

- keep startup lean
- load tool schemas only when they matter

---

## 8. Subagents and context isolation

The reference model treats subagents as isolated workers with:

- fresh context windows
- restricted tool sets
- separate execution boundaries
- summarized results returned to the parent

This is more than internal helper functions. It is a true orchestration system for delegating work.

The architectural lesson is that “multi-agent” only becomes a real platform feature when the runtime supports:

- context isolation
- tool restriction
- result summarization
- permission behavior for delegated work

---

## 9. Worktree isolation

The reference uses git worktrees as the unit of safe parallel work.

That gives each worker or session:

- a separate directory
- an independent branch
- shared git object storage

The benefit is that large changes can be decomposed safely without different tasks trampling each other in one working tree.

---

## 10. Memory model

The reference describes a layered memory system:

- global/user instructions
- project instructions
- local personal overrides
- nested path-scoped instructions
- auto memory files

The important lesson is that memory is not one monolithic file. It is a **load strategy**.

This enables:

- persistent project rules
- scoped rules that activate only for matching paths
- memory shared across future session variants

---

## 11. Permission model

The reference permission model evaluates actions in order:

1. hooks may block
2. deny rules are checked
3. allow rules are checked
4. session mode fills the gaps

This is stronger than a pure mode-based design because it allows both:

- a simple UX mode for humans
- an explicit rule system for policy and safety

The broader lesson is:

> modes are useful UX, but rules are the real policy engine

---

## 12. Context compaction

The reference compaction design is more than “summarize old messages.”

It preserves and reinjects the things that matter:

- recent exchanges
- important decisions
- file changes
- errors and test results
- instruction files
- active skills

It also includes safeguards such as failed-compaction limits so the system does not thrash.

This turns compaction into a **state-management strategy**, not just a token-reduction trick.

---

## 13. Sessions and transcripts

The pasted reference also points toward a more explicit session model with:

- session identity
- resume/fork/continue behavior
- checkpoints
- append-only transcript thinking

The main architectural lesson is that persistence should be treated as a product primitive, not an afterthought.

---

## 14. What matters most for CodeMitra

The highest-value ideas from this reference for CodeMitra are:

1. **LSP-backed intelligence**
2. **policy engine beyond simple session modes**
3. **hooks / event bus**
4. **layered settings**
5. **MCP / extensibility**
6. **true isolated subagents**
7. **smarter compaction and session persistence**

Those are the parts that move a tool from a capable local assistant to a deeper terminal agent platform.

---

## See also

- [[Vision]]
- [[Product Blueprint]]
- [[Claude Code Comparison]]
- [[Roadmap]]
