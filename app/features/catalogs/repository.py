from typing import Any, Dict, Iterable, List, Tuple

from sqlalchemy import String, Table, func, select

from app.features.catalogs.registry import CatalogSpec
from app.shared.errors import InvalidFieldError
from app.shared.repository import BaseRepository

Row = Dict[str, Any]


class CatalogRepository(BaseRepository):
    """Catalogs are Core tables read as plain dicts, so this works for any of them given its
    CatalogSpec - there is no per-catalog query code."""

    def find_rows(
        self,
        spec: CatalogSpec,
        filters: Dict[str, Any],
        sort: str,
        direction: str,
        page: int,
        per_page: int,
    ) -> Tuple[List[Row], int]:
        table = spec.table
        stmt = select(table)
        if spec.where is not None:
            stmt = stmt.where(spec.where(table))
        for key, value in filters.items():
            stmt = stmt.where(_filter_condition(table, key, value))

        total = self._session.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()

        sort_column = _column(table, sort, "sort")
        sort_column = sort_column.desc() if direction == "desc" else sort_column.asc()
        stmt = stmt.order_by(sort_column, table.c.id).offset((page - 1) * per_page).limit(per_page)
        return [dict(row) for row in self._session.execute(stmt).mappings()], total

    def find_by_ids(self, table: Table, ids: Iterable[int]) -> List[Row]:
        ids = list(ids)
        if not ids:
            return []
        return [dict(row) for row in self._session.execute(select(table).where(table.c.id.in_(ids))).mappings()]


def _column(table: Table, name: str, usage: str):
    column = table.c.get(name)
    if column is None:
        raise InvalidFieldError(f"{table.name} has no column '{name}' to {usage} by")
    return column


def _filter_condition(table: Table, key: str, value: Any):
    """null -> IS NULL, list -> IN, text on a text column -> contains (case-insensitive),
    anything else -> equals."""
    column = _column(table, key, "filter")
    if value is None:
        return column.is_(None)
    if isinstance(value, list):
        return column.in_(value)
    if isinstance(value, str) and isinstance(column.type, String):
        return column.icontains(value, autoescape=True)
    return column == value
