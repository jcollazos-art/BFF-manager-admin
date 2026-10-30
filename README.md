# bff-manager-admin

BFF (FastAPI + SQLAlchemy) for the manager/admin tooling, reading and writing directly
against the same Postgres database `manage-admin-api` (NestJS/TypeORM) uses for the
`employee_*` tables - same role bff-lsg-placement plays for its own database, not a wrapper
around manage-admin-api's own REST API.

The design rationale (what we kept from bff-lsg-placement, what we changed, and why) lives
in [`ARQUITECTURA_NUEVO_PROYECTO.md`](./ARQUITECTURA_NUEVO_PROYECTO.md) - read that first.
In short:

- **Track A** (`app/features/*/models.py`): declarative SQLAlchemy ORM with `relationship()`
  for anything that is "get/edit this entity and its children" - see `features/employee` for
  the worked example (a single `GET /v1/employee/persons/{id}` replaces 7 separate hand-written
  Retool queries via one `selectinload` query).
- **Track B** (a feature's `reports.py`, none yet in this repo): raw SQL/Core for pivots,
  dashboards, anything that aggregates across many rows - deliberately untouched by Track A.
- **`app/shared/`**: the cross-cutting pieces every feature reuses instead of
  redeclaring - `errors.py` (AppError + code/detail), `responses.py` (`Page[T]`/`Envelope[T]`),
  `pagination.py` (`Pagination`/`Sort`, exposed as configurable dependency *factories*, not
  fixed values - see section 6.4 of the doc), `query_filters.py`, `repository.py` (`BaseRepository`),
  `projection.py`, `permissions.py` (stub - no auth feature exists yet), `middleware.py`.

## Local setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in DB_* for the target Postgres instance
uvicorn app.main:app --reload
```

Swagger UI: http://127.0.0.1:8000/docs

## Tests

Not implemented yet - intentionally deferred. When they come back, the plan is integration
tests against a real engine (in-memory SQLite or a testcontainer) rather than hand-written
Fakes, so Track A's `relationship()`/`selectinload`/`begin_nested()` (SAVEPOINT) mechanics are
exercised as they really run.

## What's implemented vs. what's a placeholder

- `features/employee` is fully implemented: the nested entity view and every write operation
  listed in the architecture doc's Employee demo (insert one / update one / bulk update / bulk
  upsert / bulk delete, per sub-entity).
- No auth feature exists yet - `shared/permissions.py` is a stub showing the intended
  "decorator is sugar over `Depends`" shape (section 6.3 of the doc), not a real permission
  check. Wire a real auth feature in and put `Depends(get_current_user)` on each router the
  same way bff-lsg-placement does, before this is exposed anywhere that matters.
- `employee_comments`, `employee_person_comments`, `company_tech_partners` and
  `cost_employee_history` were in the schema data but had no read/write operation specified for
  them - left out rather than guessed at. Add them the same way as the rest once there's a
  concrete requirement.
- Catalog/lookup tables referenced by id only (`general_seniorities`, `general_languages`,
  `general_language_levels`, `general_hardwares`, `technologies`, `general_cities`, roles) are
  not modeled here - same convention as bff-lsg-placement's cross-feature catalog ids (plain
  int column, no FK/relationship, resolved by whichever feature owns that catalog).
