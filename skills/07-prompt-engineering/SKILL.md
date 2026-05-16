---
name: prompt-engineering
description: Design, review, or improve prompts for LLM applications. Use for system prompts, developer prompts, tool-use instructions, JSON schemas, few-shot examples, fallback behavior, citation rules, and prompt tests.
---

# Prompt Engineering

## Rules

- Define role, task, inputs, constraints, and output format.
- Prefer structured output schemas for machine-read results.
- Include refusal, fallback, and uncertainty behavior.
- Keep prompts testable with representative examples.
- Avoid hidden assumptions and vague success criteria.

## Workflow

1. Inspect current prompt and caller code.
2. Identify required inputs and output contract.
3. Draft concise prompt sections.
4. Add two representative examples when useful.
5. Add tests for parsing, invalid input, and fallback behavior.
