---
name: fastapi-backend
description: Build, modify, or review FastAPI backends. Use for API endpoints, routers, services, repositories, Pydantic schemas, dependency injection, validation, error handling, logging, tests, and API documentation.
---

# FastAPI Backend

## Rules

- Keep route handlers thin.
- Put business logic in services.
- Put persistence in repositories or data-access modules.
- Use Pydantic request/response schemas.
- Return proper HTTP status codes.
- Validate inputs at the boundary.
- Avoid hardcoded secrets.
- Add or update pytest coverage for behavior changes.

## Workflow

1. Inspect existing router/service/repository patterns.
2. Add schema and service logic before wiring the route.
3. Add logging and explicit error handling.
4. Add tests with `TestClient` or existing test helpers.
5. Update docs only when API usage or setup changes.
