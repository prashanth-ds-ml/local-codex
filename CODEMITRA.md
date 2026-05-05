# Project Rules

<!-- CodeMitra will follow these rules in every response. -->

## General
- Always write clean, readable, well-structured code
- Use meaningful names for variables, functions, and files
- Keep functions small and focused on a single responsibility
- Add comments only where the intent is not obvious from the code
- Do not delete files without explicit permission

## Project Management
- Always check if a file or folder exists before creating it
- Ask for the project path if not provided
- Create a virtual environment before installing any packages
- Update requirements.txt / package.json when adding dependencies

## AI / ML Projects
- Use clear, modular pipeline design (data → model → eval → serve)
- Log experiments with enough detail to reproduce results
- Keep model configs separate from code (use config files or env vars)
- Document dataset sources and any preprocessing steps

## Web / API Projects
- Separate concerns: routes → services → data layer
- Validate all inputs at the boundary
- Never hardcode secrets — use .env files
- Write at least one test per endpoint

## Safety
- Show a diff or summary before applying bulk changes
- Run tests before marking any task as complete
- Confirm before running destructive commands
