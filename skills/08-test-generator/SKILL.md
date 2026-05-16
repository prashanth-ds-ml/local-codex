---
name: test-generator
description: Add or improve tests for changed behavior. Use for pytest, FastAPI TestClient tests, database mocks, regression tests, edge cases, invalid inputs, command workflows, and changed-file test impact analysis.
---

# Test Generator

## Rules

- Identify the behavior changed before writing tests.
- Prefer focused regression tests over broad snapshots.
- Cover success, invalid input, missing data, and failure paths.
- Use existing fixtures and test style.
- Keep tests deterministic and offline where possible.

## Workflow

1. Inspect nearby tests and fixtures.
2. Add the smallest tests that protect the new behavior.
3. Include a regression test for the bug or user workflow when relevant.
4. Run targeted tests first, then the broader suite when risk justifies it.
