"""Custom SQL lives in `.sql` files next to the feature that uses it
(`features/<feature>/sql/<name>.sql`) and is run from that feature's `custom_repository.py`. See "SQL
propio" in section 5 of ARQUITECTURA_NUEVO_PROYECTO.md.

Rules: values go in as bind parameters (`:person_id`), never formatted into the string; every
table a file touches is declared in some models.py/tables.py (so tests create it and the drift
test watches it); tests/test_sql_files.py checks every file against the test database.
"""

from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from sqlalchemy import TextClause, text
from sqlalchemy.orm import Session

from app.shared.errors import InvalidFieldError

FEATURES_DIR = Path(__file__).resolve().parent.parent / "features"

Row = Dict[str, Any]


def load_sql(module_file: str, name: str) -> TextClause:
    """`load_sql(__file__, "person_summary")` reads `sql/person_summary.sql` next to the
    calling module. Call it at module level so the file is read once, at import."""
    return text((Path(module_file).parent / "sql" / f"{name}.sql").read_text())


def all_sql_files() -> List[Path]:
    return sorted(FEATURES_DIR.glob("*/sql/*.sql"))


def fetch_one(db: Session, statement: TextClause, **params: Any) -> Optional[Row]:
    row = db.execute(statement, params).mappings().one_or_none()
    return dict(row) if row else None


def fetch_all(db: Session, statement: TextClause, **params: Any) -> List[Row]:
    return [dict(row) for row in db.execute(statement, params).mappings()]


def fetch_page(
    db: Session,
    statement: TextClause,
    params: Dict[str, Any],
    *,
    page: int,
    per_page: int,
    sortable: Iterable[str],
    sort: str,
    direction: str = "asc",
    tiebreaker: str = "id",
) -> Tuple[List[Row], int]:
    """Paginates and sorts a `.sql` file without touching it: the file is wrapped as a
    subquery for the count and for ORDER BY/LIMIT/OFFSET. `sort` must be one of `sortable`
    (output column names of the file), so a caller can never inject SQL through it.
    `tiebreaker` keeps pages stable when the sort column has repeated values."""
    if sort not in sortable:
        raise InvalidFieldError(f"cannot sort by '{sort}' (allowed: {', '.join(sorted(sortable))})")
    if direction not in ("asc", "desc"):
        raise InvalidFieldError(f"direction must be 'asc' or 'desc', not '{direction}'")

    # Newlines around the inner SQL so a trailing `-- comment` can't swallow the wrapper.
    inner = statement.text.strip().rstrip(";")
    total = db.execute(text(f"SELECT count(*) FROM (\n{inner}\n) AS q"), params).scalar_one()
    rows = db.execute(
        text(
            f'SELECT * FROM (\n{inner}\n) AS q ORDER BY q."{sort}" {direction}, q."{tiebreaker}" '
            "LIMIT :_limit OFFSET :_offset"
        ),
        {**params, "_limit": per_page, "_offset": (page - 1) * per_page},
    ).mappings()
    return [dict(row) for row in rows], total
