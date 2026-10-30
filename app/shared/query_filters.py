import json
from typing import Any, Dict, Iterable, Optional

from fastapi import Request
from pydantic import BaseModel

DEFAULT_FILTER_EXCLUDE = {"page", "per_page", "relations", "sort_field", "sort_direction", "fields"}


def _coerce_string_to_list(value: Any) -> Any:
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            try:
                return json.loads(stripped)
            except (json.JSONDecodeError, ValueError):
                inner = stripped[1:-1]
                if inner:
                    return [item.strip() for item in inner.split(",")]
    return value


def _coerce_all_filters(filters: dict) -> dict:
    for key, value in filters.items():
        filters[key] = _coerce_string_to_list(value)
    return filters


def merge_query_filters(request: Request, dto: BaseModel, exclude: Optional[Iterable[str]] = None) -> Dict[str, Any]:
    """Lets a feature's own FilterX model declare only its named fields, while any extra
    querystring param the caller sends still reaches the filters dict - so adding a new ad
    hoc filter doesn't require touching the controller signature. Ported as-is from
    bff-lsg-placement, where this already proved itself (see ARCHITECTURA_NUEVO_PROYECTO.md
    section 6.4)."""

    if exclude is None:
        exclude = DEFAULT_FILTER_EXCLUDE

    filters = dto.model_dump(exclude_none=True)

    for key in request.query_params.keys():
        if key in exclude:
            continue
        if key in filters:
            continue
        values = request.query_params.getlist(key)
        if len(values) == 1:
            filters[key] = values[0]
        else:
            filters[key] = values

    return _coerce_all_filters(filters)
