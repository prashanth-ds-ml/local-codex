---
title: Roadmap
tags: [roadmap, planning, phases]
aliases: [Build Plan, Phases]
---

# Roadmap

CodeMitra is being built incrementally, one capability layer at a time. Each phase is self-contained and testable before the next begins.

---

## Phase 1 — Project foundation ✅

- [x] Project structure (`app/`, `misc/`, `pyproject.toml`)
- [x] `codemitra` CLI entry point
- [x] Virtual environment + dependencies
- [x] Config module (model names)
- [x] Banner with ASCII avatar and taglines

---

## Phase 2 — Chat core ✅

- [x] `get_chat_llm()` — `qwen2.5-coder:7b`
- [x] `get_agent_llm()` — `qwen3.5:latest`
- [x] System prompt
- [x] In-memory message history
- [x] Chat loop (input → LLM → Rich panel)

---

## Phase 3 — Filesystem agent ✅

- [x] Tool: `create_folder`
- [x] Tool: `create_file`
- [x] Tool: `read_file`
- [x] Tool: `list_directory`
- [x] Tool: `delete_file`
- [x] Tool: `delete_folder`
- [x] Tool: `move_file`
- [x] Tool: `create_venv`
- [x] Tool: `install_packages`
- [x] Tool: `run_command`
- [x] `PermissionGuard` — workspace + command whitelist
- [x] Agent loop (LLM → tool calls → results → repeat)
- [x] `ToolResult`, `AgentResponse`, `render()` templates

---

## Phase 4 — Routing ⚠️

- [x] Verified agent model supports structured tool calling
- [x] `setup_project` routing tool bound to chat LLM
- [x] Main loop handles `tool_calls` → delegates to filesystem agent
- [x] Follow-up reply after agent completes
- [ ] End-to-end test with `qwen3.5:latest` as agent

---

## Phase 5 — Code reader agent ⬜

Tools to add / reuse:
- [ ] `read_file` (reuse)
- [ ] `list_directory` (reuse)
- [ ] `search_in_files` — grep pattern across a directory
- [ ] `get_file_tree` — full nested directory tree as text

Agent behaviour:
- [ ] System prompt tuned for code understanding
- [ ] Can answer: "what does X do?", "find where Y is called", "summarise this file"
- [ ] Routing: chat LLM detects code-reading intent → delegates

---

## Phase 6 — Shell agent ⬜

- [ ] `run_command` (reuse, extended)
- [ ] Streaming stdout back to the LLM mid-run
- [ ] Timeout + kill handling
- [ ] Routing: "run the tests", "start the server", "build the project"

---

## Phase 7 — Planner agent ⬜

- [ ] Takes a large, multi-step task
- [ ] Breaks it into an ordered list of sub-tasks
- [ ] Routes each sub-task to the correct agent (filesystem / code reader / shell)
- [ ] Collects results, handles partial failures, writes a summary

---

## Phase 8 — Memory ⬜

- [ ] Session log saved to `.codemitra/history.jsonl`
- [ ] Project context file `.codemitra/context.md` (auto-updated)
- [ ] Load context on startup so the LLM knows the project
- [ ] Cross-session memory: "last time we worked on X"

---

## Summary table

| Phase | Description | Status |
|---|---|---|
| 1 | Foundation | ✅ Done |
| 2 | Chat core | ✅ Done |
| 3 | Filesystem agent | ✅ Done |
| 4 | Routing | ⚠️ Partial |
| 5 | Code reader agent | ⬜ Next |
| 6 | Shell agent | ⬜ Planned |
| 7 | Planner agent | ⬜ Planned |
| 8 | Memory | ⬜ Planned |
