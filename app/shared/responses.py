from typing import Generic, List, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    """Standard shape for every paginated list endpoint - declared once so it can be used
    as `response_model=Page[SomeOut]`, which gets the exact response shape documented in
    OpenAPI/Swagger for free (see ARCHITECTURA_NUEVO_PROYECTO.md section 6.2)."""

    data: List[T]
    total: int
    page: int
    per_page: int


class Envelope(BaseModel, Generic[T]):
    """Standard shape for a single-entity response (e.g. a nested "get one" view)."""

    data: T
