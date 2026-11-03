from typing import Any, Dict, List, Optional

from app.features.catalogs.registry import CATALOGS, CatalogSpec
from app.features.catalogs.repository import CatalogRepository, Row
from app.features.catalogs.schemas.request import CatalogRequest
from app.shared.errors import InvalidFieldError

# {"category": {"parent": {}}, "country": {}} for "category.parent,country"
RelationTree = Dict[str, "RelationTree"]


def get_catalogs(repo: CatalogRepository, requests: List[CatalogRequest]) -> Dict[str, Dict[str, Any]]:
    """Loads every requested catalog over the request's single DB connection. Best-effort:
    a bad request (unknown catalog/column/relation, or a query error) fails only its own
    entry. Each one runs in a SAVEPOINT because Postgres aborts the whole transaction after
    any failed statement, which would otherwise fail every catalog after it."""
    results: Dict[str, Dict[str, Any]] = {}
    for item in requests:
        spec = CATALOGS.get(item.catalog)
        if spec is None:
            results[item.key] = {"ok": False, "error": f"unknown catalog '{item.catalog}'"}
            continue

        savepoint = repo.savepoint()
        try:
            rows, total = repo.find_rows(
                spec, item.filters, item.sort or spec.default_sort, item.direction, item.page, item.per_page,
            )
            _attach_relations(repo, spec, rows, _parse_relations(item.relations))
        except Exception as exc:
            savepoint.rollback()
            results[item.key] = {"ok": False, "error": str(exc)}
        else:
            savepoint.commit()
            results[item.key] = {"ok": True, "data": rows, "total": total, "page": item.page, "per_page": item.per_page}
    return results


def _parse_relations(relations: Optional[str]) -> RelationTree:
    tree: RelationTree = {}
    for path in filter(None, (part.strip() for part in (relations or "").split(","))):
        node = tree
        for name in path.split("."):
            node = node.setdefault(name, {})
    return tree


def _attach_relations(repo: CatalogRepository, spec: CatalogSpec, rows: List[Row], tree: RelationTree) -> None:
    """One `WHERE id IN (...)` query per relation and level (like selectinload), then each
    row gets the related row under the relation's name, or None."""
    for name, children in tree.items():
        relation = spec.relations.get(name)
        if relation is None:
            available = ", ".join(spec.relations) or "none"
            raise InvalidFieldError(f"{spec.table.name} has no relation '{name}' (available: {available})")

        target = CATALOGS[relation.catalog]
        related = repo.find_by_ids(target.table, {row[relation.fk] for row in rows if row[relation.fk] is not None})
        _attach_relations(repo, target, related, children)

        by_id = {row["id"]: row for row in related}
        for row in rows:
            row[name] = by_id.get(row[relation.fk])
