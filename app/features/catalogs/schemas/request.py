from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, model_validator

DEFAULT_PER_PAGE = 20
MAX_PER_PAGE = 500


class CatalogRequest(BaseModel):
    """One catalog to load. `filters` keys are the catalog's columns: null -> IS NULL,
    list -> IN, text -> contains (case-insensitive), anything else -> equals."""

    catalog: str
    alias: Optional[str] = None  # key in the response; set it to load the same catalog twice
    filters: Dict[str, Any] = {}
    page: int = Field(1, ge=1)
    per_page: int = Field(DEFAULT_PER_PAGE, ge=1, le=MAX_PER_PAGE)
    sort: Optional[str] = None  # defaults to the catalog's own (see registry.py)
    direction: Literal["asc", "desc"] = "asc"
    relations: Optional[str] = None  # comma separated, dots for nesting: "country,category.parent"

    @property
    def key(self) -> str:
        return self.alias or self.catalog


class CatalogBatchRequest(BaseModel):
    requests: List[CatalogRequest] = Field(..., min_length=1, max_length=50)

    @model_validator(mode="after")
    def keys_are_unique(self) -> "CatalogBatchRequest":
        keys = [item.key for item in self.requests]
        duplicated = sorted({key for key in keys if keys.count(key) > 1})
        if duplicated:
            raise ValueError(f"duplicated catalog keys {duplicated} - use `alias` to load a catalog twice")
        return self
