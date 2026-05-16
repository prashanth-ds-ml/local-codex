---
name: repo-analyzer
description: Analyze a new or existing repository before making changes. Use for requests to understand repo structure, entry points, API routes, data models, test commands, risky files, architecture, dependencies, or current project state.
---

# Repo Analyzer

## Workflow

1. Inspect `README*`, package/config files, app entry points, tests, docs, and top-level folders.
2. Identify the runtime stack, package manager, entry points, test commands, and deployment hints.
3. Map major modules by responsibility.
4. Find risky files: auth, persistence, config, migrations, external APIs, generated artifacts, and large files.
5. Produce a concise summary before proposing edits.

## Output

- Purpose and stack
- How to run
- How to test
- Main modules and data flow
- Risk areas
- Next recommended action
