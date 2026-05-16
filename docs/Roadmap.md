---
title: Roadmap
tags: [roadmap, planning, phases]
aliases: [Build Plan, Phases]
---

# Roadmap

CodeMitra is being built incrementally, one capability layer at a time. Each phase is self-contained and testable before the next begins.

This doc is the **implementation sequence**. For product behavior targets, use [[Product Blueprint]]. For the Claude-specific benchmark and gaps, use [[Claude Code Reference]] and [[Claude Code Comparison]].

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

## Phase 10 — Trust layer: diff preview + approvals 🔲

- [x] Show diff/summary before bulk file writes (confirm Y/N)
- [x] Add explicit permission modes (`read-only`, `plan`, `approve`, `auto`)
- [x] Separate approvals for file edits and shell commands, with workspace scope still enforced
- [x] Add undo / rewind for the last change set

---

## Phase 11 — Repair loop + operator commands 🔲

- [x] `/fix <command>` — run a bounded repair loop against a failing command
- [x] `run pytest -> read failures -> generate fix -> run again` loop (max 3 attempts)
- [x] `/diff` — inspect pending changes
- [x] `/review` — run reviewer agent on changed files or the last CodeMitra change set
- [x] `/explain <file>` — explain what a file does

---

## Phase 12 — Session UX 🔲

- [x] Named sessions
- [x] `/resume`, `/history`, `/rename`
- [x] Better task / progress timeline in the terminal UI
- [x] Clear model, usage, and current-task visibility
- [x] Persistent prompt toolbar with mode, model, cwd, context load, and task state
- [x] `/context` for live context-window usage
- [x] `/permissions` for live policy visibility
- [x] `/hibernate` for low-memory recovery after saving session state
- [x] Prompt-in-editor with `Ctrl+G`
- [x] Background shell tasks with `/run --background <cmd>` and `/tasks`
- [x] Plan-step checkpoint in session metadata so `/resume` can show interrupted or completed plan execution state
- [x] Explicit plan approval and controls with `/plan approve`, `/plan next`, `/plan run`, and `/plan pause`
- [x] Compaction checkpoint in session metadata so `/resume` can show the last manual or automatic compact event
- [ ] Improve `/compact` and automatic compaction controls and previews

---

## Phase 13 — Project auto-detect + code intelligence 🔲

- [x] On startup, scan README + entry points + file tree
- [x] Inject a concise project brief as startup context so the LLM knows the workspace without being told
- [ ] Skip manual `/context` load for known project layouts
- [x] Add a dedicated symbol lookup / references workflow
- [ ] Add LSP-backed diagnostics when available

---

## Phase 14 — Extensibility + policy controls ✅ In progress

- [x] Configurable allowed directories and tool policies
- [x] Project-level instruction loading from configured workspace files
- [x] Workspace CodeMitra skill discovery with `/skills` and `/skills show <name>`
- [ ] MCP server support
- [ ] Plugin or custom slash command extension points

---

## Phase 15 — Git-aware workflows 🔲

- [x] Git diff-aware review flow
- [x] Branch-aware `/status` summary with upstream and working-tree counts
- [x] Commit-readiness summary in `/status`
- [ ] Commit message / commit-content summaries
- [ ] Stronger review-before-commit workflow
- [ ] Optional IDE / editor handoff later

---

## Current next steps

1. **Code intelligence + extensibility** — LSP-backed diagnostics and MCP hooks
2. **Git workflow depth** — commit message summaries and stronger review-before-commit
3. **Compaction polish** — add clearer `/compact` controls and previews on top of the saved checkpoint
4. **Plan execution polish** — continue refining approval and resume edge cases as real sessions expose them

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
| 10 | Trust layer: diff preview + approvals | ✅ Done |
| 11 | Repair loop + operator commands | ✅ Done |
| 12 | Session UX | ✅ Mostly done |
| 13 | Project auto-detect + code intelligence | ✅ In progress |
| 14 | Extensibility + policy controls | ✅ In progress |
| 15 | Git-aware workflows | ✅ In progress |

---

## See also

- [[Vision]]
- [[Product Blueprint]]
- [[Claude Code Reference]]
- [[Claude Code Comparison]]
