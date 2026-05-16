---
name: mongodb-data-layer
description: Design, implement, or review MongoDB access. Use for collections, repositories, indexes, ObjectId handling, query performance, schema changes, timestamps, projections, migrations, and tests around persistence.
---

# MongoDB Data Layer

## Rules

- Keep database access out of route handlers.
- Validate `ObjectId` values before querying.
- Use projections when full documents are not needed.
- Avoid unbounded queries; require limits or pagination.
- Add indexes for common filters and sort fields.
- Store `created_at` and `updated_at` where records are mutable.
- Document schema changes and migration notes.

## Workflow

1. Inspect current database client and repository patterns.
2. Define collection shape and indexes.
3. Add repository methods with clear return types.
4. Add tests for valid, missing, invalid, and empty-result cases.
5. Note migration or backfill needs.
