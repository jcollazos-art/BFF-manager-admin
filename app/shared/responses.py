from typing import Generic, List, Optional, TypeVar

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


class BulkItemResult(BaseModel):
    index: int
    ok: bool
    id: Optional[int] = None
    error: Optional[str] = None


class BulkResponse(BaseModel):
    """Response of every bulk write: one result per item, in request order. `ok` is true
    only if every item succeeded - failed items were rolled back individually, the rest
    were saved (best-effort, see shared/repository.py)."""

    ok: bool
    results: List[BulkItemResult]

    @classmethod
    def from_results(cls, results: List[dict]) -> "BulkResponse":
        return cls(ok=all(r["ok"] for r in results), results=results)
