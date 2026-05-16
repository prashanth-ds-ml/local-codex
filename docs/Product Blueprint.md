---
title: Product Blueprint
tags: [product, ux, roadmap, benchmark, comparison]
aliases: [UX Blueprint, Competitive Baseline, Product Spec]
---

# Product Blueprint

## Why this doc exists

CodeMitra already has the core agent architecture: routing, planning, filesystem tools, shell execution, code reading, and local memory. The next step is not "more agent logic" in isolation. The next step is making the product feel safe, transparent, fast, and trustworthy in the same way the best terminal coding assistants do.

This doc captures:

1. the feature baseline from Claude Code, Codex CLI, and GitHub Copilot CLI
2. CodeMitra's current position
3. the product behavior we want CodeMitra to adopt
4. the next implementation priorities that follow from that comparison

Use related docs deliberately:

- [[Claude Code Reference]] for the Claude-style architectural reference
- [[Claude Code Comparison]] for the CodeMitra-vs-Claude gap analysis
- [[Roadmap]] for the implementation sequence

---

## Competitive baseline

| Area | Claude Code | Codex CLI | Copilot CLI | CodeMitra today | CodeMitra target |
|---|---|---|---|---|---|
| Interactive terminal UX | Strong TUI, modes, approvals, session controls | Strong TUI, approvals, slash commands | Rich terminal UX, timeline, tasks, slash commands | Strong and improving terminal UX with modes, toolbar, status, and tasks | Keep tightening flow and visibility |
| Planning before action | Yes | Yes | Yes | Yes | Keep and surface more clearly |
| Multi-file edits | Yes | Yes | Yes | Yes | Add diff-first approval flow |
| Shell execution | Yes | Yes | Yes | Yes, including tracked background tasks | Add tighter plan/task coordination |
| Codebase understanding | Yes | Yes | Yes, with LSP support | Yes | Add stronger symbol-aware navigation |
| Diff review | Yes | Yes | Yes | Yes | Deepen before-commit flow |
| Review agent | Yes | Yes | Yes | Yes | Improve git context and reporting |
| Test and fix loop | Yes | Yes | Yes | Yes | Keep improving |
| Permission modes | Strong | Strong | Strong | Strong baseline | Refine edge cases |
| Session resume | Yes | Yes | Yes | Yes | Improve compact + plan resume UX |
| Context compaction | Yes | Yes | Yes | Partial | Improve and expose clearly |
| Slash commands | Rich | Rich | Very rich | Broad working surface | Keep expanding deliberately |
| Model switching | Yes | Yes | Yes | Visible and usable | Keep |
| Subagents / task orchestration | Yes | Yes | Yes | Visible current-task + background-task UX | Make plan execution more explicit |
| Extensibility / MCP | Yes | Yes | Yes | Skills baseline; no MCP yet | Add MCP / plugin hooks |
| Git / PR awareness | Good | Good | Excellent | Minimal | Later |
| IDE / LSP integration | Some | Some | Explicit | No | Add LSP first |

---

## What CodeMitra should copy

### From Claude Code

- explicit permission modes
- strong plan-first workflow
- resumable sessions
- visible task orchestration
- trust-oriented UX where the agent explains what it wants to do before it does it

### From Codex CLI

- clean inspect -> plan -> edit -> diff -> run -> review loop
- strong approval flow for edits and commands
- `/diff` and `/review` as first-class actions
- background and parallel task mindset for larger work

### From Copilot CLI

- richer slash command surface
- session and task management
- `/plan`, `/diff`, `/review`, `/compact`, `/usage` style operator controls
- explicit directory, tool, and environment controls
- eventual LSP and GitHub-aware workflows

### What stays uniquely CodeMitra

- local-first and offline by default
- Ollama-native model selection
- markdown memory vault under `.codemitra/`
- system design over "one magic model"

---

## Current implementation priorities

### P0 - trust and repair loop

These are the highest-value changes because they move CodeMitra from "capable" to "safe and dependable".

| Priority | Feature | Why it matters |
|---|---|---|
| P0 | Diff preview before writes | Builds trust before code changes land |
| P0 | Explicit approval modes | Makes agent behavior predictable |
| P0 | Test -> fix -> retry loop | Turns edits into a real coding workflow |
| P0 | `/diff`, `/fix`, `/review` | Gives users standard operator commands |
| P0 | Undo / rewind last turn | Reduces fear of trying agent actions |

### P1 - session and operator UX

| Priority | Feature | Why it matters |
|---|---|---|
| P1 | `/resume`, `/history`, `/rename` | Makes long-running work practical |
| P1 | `/model`, `/context`, `/status`, `/permissions` | Gives users control and visibility |
| P1 | Better progress / task timeline and persistent statusline | Makes the agent's current state obvious |
| P1 | Project auto-detect on startup | Reduces repeated setup and prompting |
| P1 | Explicit plan approval, active-step tracking, interrupted-plan resume | Makes planning trustworthy and restartable |

### P2 - intelligence and extensibility

| Priority | Feature | Why it matters |
|---|---|---|
| P2 | LSP-backed code intelligence | Improves definitions, references, diagnostics |
| P2 | Configurable allowed dirs / tools | Improves permission ergonomics |
| P2 | Project instruction loading | Lets workspaces define local operating rules |
| P2 | MCP / plugin support | Extends the new skills baseline into tool and integration hooks |

### P3 - ecosystem workflows

| Priority | Feature | Why it matters |
|---|---|---|
| P3 | Git-aware review and commit helpers | Natural next layer after local trust loop |
| P3 | IDE-aware workflows | Better navigation and handoff |
| P3 | Remote / cloud task support | Optional after local UX is strong |

---

## Target behavior spec

## 1. Interaction model

Desired behavior:

1. User makes a request in natural language.
2. CodeMitra decides whether to answer directly, inspect code, ask clarifying questions, or create a plan.
3. If the task is non-trivial, CodeMitra shows a short plan before acting.
4. Before risky actions, CodeMitra explains what it wants to do and asks for approval.

Target feel:

- calm
- explicit
- low-surprise
- easy to interrupt

Current implementation baseline:

- small talk is handled separately from the heavy agent prompt when possible
- brainstorming can be routed through `/brainstorm` and saved to `.codemitra/brainstorm.md`
- raw reasoning output is hidden by default and can be shown with `/thinking on`
- session mode is explicit and inspectable with `/mode` and `/status`

---

## 2. Edit workflow

Desired default flow:

1. inspect the relevant files
2. explain the intended change briefly
3. show a diff summary
4. ask for approval
5. apply the patch
6. run validation
7. report the result
8. allow undo

Must-have commands:

- `/diff`
- `/undo`
- `/review`

Current implementation baseline:

- overwrite edits show a diff preview in `approve` mode
- `/diff` shows either git diff or the last CodeMitra-recorded change set
- `/review` runs a dedicated review agent against the current or staged git diff, or the last CodeMitra-recorded change set
- `/explain <file>` runs a dedicated explain agent for file-level understanding
- `/symbols <name>` runs a dedicated symbol-intelligence workflow over definitions and usages
- `/undo` reverts the last recorded file change set
- `auto` mode skips interactive approval for in-workspace edits
- `read-only` and `plan` modes block code-changing filesystem actions
- `allowed_roots`, `disabled_tools`, and `disabled_commands` can now be configured in `codemitra.toml`

---

## 3. Error-fixing workflow

Desired behavior:

1. User pastes a traceback or failing output.
2. CodeMitra identifies likely files and failure causes.
3. CodeMitra proposes a fix.
4. CodeMitra runs tests or the failing command.
5. CodeMitra retries up to a bounded number of times.
6. If still failing, CodeMitra stops and explains the remaining issue clearly.

Must-have command:

- `/fix`

Current implementation baseline:

- `/fix <command>` runs a bounded repair loop
- the loop reruns the failing command, asks the filesystem agent to patch, and retries up to 3 times
- the loop stops early if the command already passes, the command is denied, or no code changes were applied

---

## 4. Planning workflow

Desired behavior:

1. `/plan` enters brainstorm mode.
2. CodeMitra asks a few clarifying questions.
3. CodeMitra produces ordered steps.
4. The plan is saved to `.codemitra/plan.md`.
5. The user can approve the full plan or execute step-by-step.

Current implementation baseline:

- substantial natural-language build/debug/change requests can route into brainstorm + plan automatically
- `plan` mode saves plans without starting execution
- `read-only` mode can inspect and plan, but will not execute plan steps
- `/plan approve` explicitly approves the saved plan before execution
- `/plan next` executes exactly one approved pending step
- `/plan run` executes approved pending steps until the plan completes or execution is interrupted
- `/plan pause` records paused execution state without losing progress
- `/resume` shows plan approval, active-step checkpoint, and the next plan action after pause or interruption

---

## 5. Session UX

Desired behavior:

- named sessions
- `/resume`
- `/history`
- `/compact`
- `/hibernate`
- visible current task
- visible model and usage state

This is one of the main differences between a simple chat tool and a true coding assistant.

Current implementation baseline:

- named workspace sessions are now persisted under `.codemitra/session.json`
- `/resume` shows session name, plan state, undo state, and recent activity
- plan execution writes an active-step checkpoint into session metadata so `/resume` can surface interrupted or recently completed plan work
- `/history` shows recent saved turns from `.codemitra/activity.md`
- `/rename <name>` renames the current workspace session
- `/status` shows workspace, shell cwd, mode, reasoning visibility, plan state, usage, and undo state
- `/status` includes a branch-aware Git summary with upstream and staged / unstaged / untracked counts when the workspace is a Git repo
- `/status` reports commit readiness so users can see whether staged changes are ready or whether unstaged/untracked work remains outside the commit
- `/context` shows live context-window load and compaction threshold
- `/permissions` shows execution policy, workspace scope, and restrictions
- manual and automatic compaction save a session checkpoint so `/resume` can show when compaction happened, why, and how much history was compacted
- `/hibernate` saves workspace state, unloads the active local model, and clears in-memory chat history for low-memory recovery
- startup now auto-detects a concise workspace brief and injects it into the system prompt before the first turn
- configured project instruction files such as `AGENTS.md`, `.codemitra/instructions.md`, and `.github/copilot-instructions.md` are loaded into the startup system prompt when present
- the prompt now includes a persistent bottom toolbar with mode, model, cwd, context load, and current task
- `Ctrl+G` opens the composer in the editor for longer prompts
- prompt label now includes the active mode
- `/run --background <cmd>` now starts long-running shell work without blocking the REPL
- `/tasks`, `/tasks show <id>`, and `/tasks stop <id>` now expose tracked background work directly in the terminal
- `/status` and the prompt toolbar now surface background-task state
- `/skills` lists workspace skills discovered from `skills/*/SKILL.md` and `.codemitra/skills/*/SKILL.md`
- `/skills show <name>` displays one skill's full `SKILL.md` instructions from inside the workspace sandbox
- startup injects a compact skill index so the assistant can read and follow matching skill playbooks on demand

---

## 6. Permission model

Desired behavior:

- `read-only`
- `plan`
- `approve`
- `auto`

Permissions should be separable for:

- file edits
- shell commands
- network or web access
- outside-workspace access

Trust comes from predictability, not just capability.

Current implementation baseline:

- `read-only`: inspect only; shell subprocess execution is blocked, but shell navigation helpers still work
- `plan`: inspect and create plans; code edits and shell subprocess execution stay blocked
- `approve`: default coding mode; asks before shell commands and file changes
- `auto`: in-workspace edits and shell commands are auto-approved
- outside-workspace writes are still blocked by workspace scope rules

---

## 7. Code intelligence

Desired behavior:

- find definition
- find references
- explain a file or symbol
- surface diagnostics
- prefer precise navigation over broad grep when possible

Best implementation path:

- add LSP-backed intelligence first
- keep grep/tree fallback when LSP is unavailable

---

## 8. Extensibility

Desired behavior:

- project config file
- project instruction file
- workspace skills
- custom tools
- MCP servers
- slash command extensions

Current implementation baseline:

- `skill_dirs` config discovers workspace skill directories
- `skills/*/SKILL.md` and `.codemitra/skills/*/SKILL.md` provide reusable playbooks
- startup injects only the compact skill index
- `/skills` lists the active pack
- `/skills show <name>` displays one skill body from inside the workspace sandbox

Next extensibility work:

- MCP servers
- plugin or custom slash command extension points
- custom tools beyond markdown skill playbooks

This is how CodeMitra becomes a platform instead of a single built-in assistant.

---

## Decisions captured so far

- prefer **explicit operator control** over hidden autonomy
- keep **offline-first local execution** as the default identity
- use **session modes** as the main behavioral contract
- make risky work **visible before and during execution**
- invest in **workflow regression coverage** so UX behavior stays stable as features grow

---

## Product principle

CodeMitra does not need to copy Claude Code, Codex CLI, or Copilot CLI feature-for-feature. It should copy the parts that create trust, speed, and clarity, then adapt them to a local-first, offline, Ollama-native workflow.

---

## See also

- [[Vision]]
- [[Claude Code Reference]]
- [[Claude Code Comparison]]
- [[Roadmap]]
