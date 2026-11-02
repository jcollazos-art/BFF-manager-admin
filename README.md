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
  the worked example (a single `GET /v1/employee/details/{id}` replaces 7 separate hand-written
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

Requires **Docker running** (Docker Desktop locally). If it isn't, `pytest` stops with a
clear message instead of failing every test.

```bash
pip install -r requirements-dev.txt   # test deps, kept out of the production image
pytest                                # API tests against a throwaway Postgres 15 (~2s)
pytest -m drift                       # ORM models vs. the real database in .env (read-only)
pytest tests/features/employee/test_upsert.py -k decimal   # one file / one test
```

The first run pulls the `postgres:15-alpine` image, so it takes a bit longer.

### How it works

- **Real database, no mocks.** A disposable Postgres is started once per run and its tables
  are created from the ORM models. Tests call the real app over HTTP (`client`) and check
  what ended up in the database (`db`).
- **Nothing to clean up.** Each test runs inside a transaction that is rolled back at the
  end, so tests are independent and can run in any order.
- **Drift test.** Because the test tables come from the models, a model that disagrees with
  the real schema would go unnoticed. `pytest -m drift` catches that - run it whenever you
  touch a `models.py`. It is excluded from plain `pytest` because it needs the `.env` DB.

### Layout

```
tests/
  conftest.py                 # shared setup (container, rollback, client) - rarely touched
  test_schema_drift.py        # pytest -m drift
  shared/                     # pure helpers from app/shared
  features/<feature>/
    factories.py              # make_person(db, **overrides) ...
    test_read.py              # GET endpoints
    test_upsert.py            # bulk-upsert endpoints
    test_delete.py            # delete endpoints
```

### Writing a test

```python
def test_update_only_changes_the_fields_sent(client, db):
    person = make_person(db)                                       # 1. arrange with factories
    language = make_language(db, person, language_id=7, language_level_id=1)

    client.post("/v1/employee/languages/bulk-upsert",              # 2. call the real endpoint
                json=[{"id": language.id, "language_level_id": 2}])

    db.expunge_all()                                               # 3. read back from the DB,
    row = db.get(EmployeeLanguage, language.id)                    #    not from session memory
    assert (row.language_id, row.language_level_id) == (7, 2)
```

- Test behaviour through the endpoint, not internal functions - use cases and repositories
  get covered on the way. Unit-test only pure logic (e.g. `shared/query_filters.py`).
- Build data with factories: only pass the fields the test cares about.
- Call `db.expunge_all()` before asserting on stored rows, otherwise you may read cached
  objects instead of what was actually written.

### Adding a feature

1. Import its `models` in `tests/conftest.py` (one line) so its tables get created.
2. Add `tests/features/<feature>/factories.py` and tests for each endpoint: the happy path,
   the 404/422 cases, and any rule that lives in the repository or use case.
3. Run `pytest` and `pytest -m drift`.

More detail in the "Tests" section of the architecture doc.

## What's implemented vs. what's a placeholder

- `features/employee` is fully implemented: the nested entity view, one
  `POST /<resource>/bulk-upsert` per sub-entity that creates and/or updates one or many rows
  (item with `id` -> update, without -> create), and the separate delete endpoints - covering
  every write listed in the architecture doc's Annex A.
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
