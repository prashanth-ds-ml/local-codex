---
title: Testing Strategy
tags: [testing, qa, workflows, transcripts]
aliases: [QA Strategy, Workflow Tests]
---

# Testing Strategy

CodeMitra needs more than isolated unit tests. It is a **terminal product with routing, agents, tools, session state, and UX flows**, so the testing strategy must validate both individual components and full user journeys.

This document defines:

1. what we test
2. how we test it
3. the standard workflows CodeMitra should reliably follow
4. the first regression cases that should never break again

## Current baseline

- **Validated suite:** 337 passing tests
- **Workflow packs now covered:** bootstrap, understand, session lifecycle, navigation, plan lifecycle, safe edit, fix loop, research, safety/approval, background task UX
- **Primary testing decision:** protect operator-facing workflows first, then backfill helper and unit coverage as needed

---

## Why this exists

Transcript-driven bugs often do not come from one broken function. They usually come from a **bad interaction between routing, state, tools, and UX**.

Example:

- user asks for actionable setup work
- brainstorm keywords appear in the same sentence
- routing chooses brainstorm instead of execution or planning
- CodeMitra talks about the work instead of doing it

That kind of issue is hard to catch with helper-only tests. It needs transcript and workflow coverage.

---

## Test pyramid for CodeMitra

### 1. Unit tests

Validate small helpers and decision logic.

Examples:

- intent classification
- navigation target extraction
- model inventory filtering
- context and permission replies
- project auto-detect helpers

Goal:

- fast feedback
- precise regressions
- deterministic coverage of edge cases

### 2. Integration tests

Validate agent + tool loops together.

Examples:

- filesystem agent with permission guard
- shell agent execution and summaries
- reader agent search/read flow
- web agent fetch/search flow
- planner writing and executing steps

Goal:

- confirm components work correctly in combination
- verify tool loops, summaries, and guardrails

### 3. Transcript tests

Validate real prompts against expected behavior paths.

These should assert:

- which intent is chosen
- whether a request should brainstorm, plan, inspect, or execute
- which command/agent path is taken
- whether the terminal behavior matches user intent

Examples:

- “create a folder named Med_RAG and make .venv ...”
- “go to snake-game and understand it”
- “search this URL”
- “fix pytest failure”

Goal:

- prevent natural-language regressions
- keep the product aligned with actual user phrasing

### 4. Workflow tests

Validate full multi-step sessions end to end.

These should cover:

- setup
- planning
- execution
- review
- recovery
- resume

Goal:

- prove CodeMitra behaves correctly over real operator journeys
- catch issues between turns, not just within a single function

---

## What every major component needs

| Area | Must verify |
|---|---|
| Startup | model picker, auto-detect, session snapshot, workspace context |
| Routing | chat vs brainstorm vs change vs explain vs plan vs run |
| Filesystem agent | file ops, `.venv`, docs setup, approvals, denied actions |
| Shell agent | cwd, command execution, trust, timeout, failures |
| Reader agent | file read, symbol lookup, search, explanations |
| Web agent | URL fetch, search, failures, summaries |
| Planner | plan creation, execution gating, resume state |
| Memory/session | context, activity, plan, compact, hibernate, resume |
| UX | progress messages, statusline, silent-gap handling, prompt affordances |

---

## Standard CodeMitra workflows

These workflows should become stable product behaviors and test targets.

### Workflow 1 — Bootstrap Project

1. detect workspace
2. create target folder
3. create `.venv`
4. initialize docs / memory vault
5. confirm created structure

### Workflow 2 — Understand Project

1. auto-detect project shape
2. inspect key files
3. summarize purpose, entrypoint, dependencies, blockers, next steps

### Workflow 3 — Plan Work

1. clarify when needed
2. write plan
3. show plan clearly
4. wait for approval or execute first step

### Workflow 4 — Safe Edit

1. inspect
2. explain intended change
3. show diff / summary
4. approve
5. apply
6. validate
7. offer undo path

### Workflow 5 — Fix Failure

1. reproduce
2. inspect
3. patch
4. rerun
5. stop clearly if unresolved

### Workflow 6 — Research

1. search or fetch
2. read sources
3. summarize findings
4. suggest next step

### Workflow 7 — Recover Session

1. persist state
2. compact or hibernate
3. resume from saved workspace context

### Workflow 8 — Manage Background Work

1. start long-running shell work without blocking the REPL
2. surface task state in `/tasks`, `/status`, and the toolbar
3. inspect recent output
4. stop work explicitly when needed

---

## First regression pack to build

This is the highest-value initial suite.

### A. Intent-routing regression pack

Must protect against:

- actionable setup request incorrectly going to brainstorm
- navigation request being swallowed as chat
- explain request going to raw model instead of deterministic summary
- URL request not routing to web fetch

### B. Project bootstrap workflow pack

Must cover:

1. start from parent folder
2. create project folder
3. create `.venv`
4. initialize docs / memory structure
5. verify created state

### C. Session lifecycle pack

Must cover:

- startup auto-detect
- `/resume`
- `/compact`
- `/hibernate`
- memory persistence

### D. Safety pack

Must cover:

- approval prompts
- denied file actions
- denied shell actions
- outside-workspace restrictions

---

## Transcript-derived regression cases

These should be kept permanently once added.

### Case: Med_RAG setup request

Prompt:

`create a folder named Med_RAG and make .venv in that folder and setup obsidian and other docs that will help us start planning and brainstorming our ideas and build the project`

Expected behavior:

- **must not** route to brainstorm
- should route to **change** or **plan-first execution**
- should create or begin executing the requested setup flow

Why it matters:

- this is a realistic startup request
- it mixes setup with planning language
- it exposed a real routing weakness

---

## Principle

CodeMitra should not only pass helper tests. It should pass **operator reality**:

- what users actually type
- what the terminal actually shows
- what state survives across turns
- what fails safely when an action is denied or interrupted

- natural prompts
- multi-step work
- interruptions
- approvals
- recovery
- session continuity

That is the testing standard for the product going forward.
