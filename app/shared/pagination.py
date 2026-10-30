from dataclasses import dataclass
from typing import Optional

from fastapi import Query


@dataclass
class Pagination:
    page: int
    per_page: int


@dataclass
class Sort:
    sort_field: Optional[str]
    sort_direction: str


def pagination_params(default_per_page: int = 20, max_per_page: int = 200):
    """Factory, not a fixed dependency: the validation rule (page >= 1, per_page bounded)
    lives here once, but each router can ask for different defaults/bounds explicitly in
    its own route - e.g. an export endpoint that legitimately needs a much larger
    `per_page` - without redeclaring `Query(...)` or forking `Pagination`
    (ARCHITECTURA_NUEVO_PROYECTO.md section 6.4)."""

    def dependency(
        page: int = Query(1, ge=1),
        per_page: int = Query(default_per_page, ge=1, le=max_per_page),
    ) -> Pagination:
        return Pagination(page=page, per_page=per_page)

    return dependency


def sort_params(default_field: Optional[str] = None, default_direction: str = "asc"):
    def dependency(
        sort_field: Optional[str] = Query(default_field),
        sort_direction: str = Query(default_direction, pattern="^(asc|desc)$"),
    ) -> Sort:
        return Sort(sort_field=sort_field, sort_direction=sort_direction)

    return dependency
