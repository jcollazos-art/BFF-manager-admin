from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class CatalogResult(BaseModel):
    """`ok: false` carries only `error`; the other catalogs of the batch are unaffected."""

    ok: bool
    data: Optional[List[Dict[str, Any]]] = None
    total: Optional[int] = None
    page: Optional[int] = None
    per_page: Optional[int] = None
    error: Optional[str] = None


class CatalogBatchResponse(BaseModel):
    """`results` is keyed by each request's `alias` or `catalog`. `ok` is true only if every
    catalog loaded."""

    ok: bool
    results: Dict[str, CatalogResult]
