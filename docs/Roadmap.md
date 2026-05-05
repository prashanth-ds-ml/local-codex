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

## Phase 5 — Code reader agent ✅

- [x] `read_file` (reuse)
- [x] `list_directory` (reuse)
- [x] `search_in_files` — grep pattern across a directory
- [x] `get_file_tree` — full nested directory tree as text
- [x] `find_definition` — locate def/class/constant by name
- [x] `grep_symbol` — find all usages of a symbol

Agent behaviour:
- [x] System prompt tuned for code understanding
- [x] Can answer: "what does X do?", "find where Y is called", "summarise this file"
- [x] Routing: chat LLM detects code-reading intent → delegates

---

## Phase 6 — Shell agent ✅

- [x] `run_command` (reuse, extended)
- [x] Streaming stdout back to the LLM mid-run
- [x] Timeout + kill handling
- [x] Command whitelist (`python`, `pytest`, `git`, `npm`, `ruff`, `mypy`, `black`, `uvicorn`, …)
- [x] `ShellResult` — exit code, output, timed_out, denied flags
- [x] Routing: "run the tests", "start the server", "build the project"

---

## Phase 7 — Planner agent ✅

- [x] Takes a large, multi-step task
- [x] Breaks it into an ordered list of sub-tasks
- [x] Routes each sub-task to the correct agent (filesystem / code reader / shell)
- [x] Collects results, handles partial failures, writes a summary
- [x] Writes and reads `.codemitra/plan.md` with completion markers

---

## Phase 8 — Memory ✅

- [x] `.codemitra/activity.md` — append-only activity log
- [x] `.codemitra/context.md` — project context (editable)
- [x] `.codemitra/plan.md` — active plan with step checkboxes
- [x] `.codemitra/README.md` — vault index
- [x] Load context on startup so the LLM knows the project
- [x] Cross-session memory: context persists between sessions

---

## Phase 9 — Brainstorm loop ✅

- [x] `/plan` runs clarifying Q&A before generating plan steps
- [x] Up to 5 rounds of questions (max 3 questions per round)
- [x] `READY_TO_PLAN` signal when model has enough context
- [x] Full Q&A context passed to `create_plan()` for specific steps

---

## Phase 10 — Diff preview + test loop 🔲

- [ ] Show diff/summary before bulk file writes (confirm Y/N)
- [ ] `run pytest → read failures → generate fix → run again` loop (max 3 attempts)
- [ ] `/fix <paste error>` slash command shortcut

---

## Phase 11 — Slash command shortcuts 🔲

- [ ] `/explain <file>` — explain what a file does
- [ ] `/fix <error>` — paste traceback, get fix applied
- [ ] `/review` — run reviewer agent on changed files

---

## Phase 12 — Project auto-detect 🔲

- [ ] On startup, scan README + entry points + file tree
- [ ] Inject as context so LLM knows the project without being told
- [ ] Skip manual `/context` load for known project layouts

---

## Summary table

| Phase | Description | Status |
|---|---|---|
| 1 | Foundation | ✅ Done |
| 2 | Chat core | ✅ Done |
| 3 | Filesystem agent | ✅ Done |
| 4 | Routing | ✅ Done |
| 5 | Code reader agent | ✅ Done |
| 6 | Shell agent | ✅ Done |
| 7 | Planner agent | ✅ Done |
| 8 | Memory vault | ✅ Done |
| 9 | Brainstorm loop | ✅ Done |
| 10 | Diff preview + test loop | 🔲 Next |
| 11 | Slash command shortcuts | 🔲 Planned |
| 12 | Project auto-detect | 🔲 Planned |
