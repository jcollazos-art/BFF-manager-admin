"""Which catalogs POST /catalogs can serve, and how each one behaves.

Every table in tables.py is a catalog automatically, named without its `general_` prefix
(`general_cities` -> "cities") and sorted by `order`, else `name`, else `id`. Adding a catalog
is only adding its table. Anything specific to one catalog goes in `_CUSTOM`:

- `relations`: foreign keys the caller can expand with `"relations": "country"` (nested with
  dots: "category.parent"). The database declares no FKs, so they're listed here by hand.
- `default_sort`: overrides the automatic one.
- `where`: a condition always applied, e.g. hiding soft-deleted rows.
"""

from dataclasses import dataclass, field
from typing import Callable, Dict, Optional

from sqlalchemy import ColumnElement, Table

from app.features.catalogs import tables


@dataclass(frozen=True)
class Relation:
    catalog: str  # catalog the foreign key points to
    fk: str  # column on this catalog holding the related row's id


@dataclass(frozen=True)
class CatalogSpec:
    table: Table
    default_sort: str
    relations: Dict[str, Relation] = field(default_factory=dict)
    where: Optional[Callable[[Table], ColumnElement]] = None


_CUSTOM: Dict[str, dict] = {
    "account_phases": dict(relations={
        "account_type": Relation("account_types", "account_type_id"),
        "account_status": Relation("account_statuses", "account_status_id"),
    }),
    "attachment_subtype": dict(relations={"type": Relation("attachment_type", "type_id")}),
    "cities": dict(relations={"country": Relation("countries", "country_id")}),
    "cost_centers": dict(relations={"profit_loss": Relation("profit_and_loss", "profit_loss_id")}),
    "exceptions": dict(relations={"exception_type": Relation("exception_types", "exception_type_id")}),
    "governance_concept_type_values": dict(relations={
        "concept_type": Relation("governance_concept_types", "concept_type_id"),
    }),
    "governance_concepts": dict(relations={
        "category": Relation("governance_categories", "category_id"),
        "concept_type": Relation("governance_concept_types", "concept_type_id"),
    }),
    "metrics": dict(where=lambda table: table.c.deleted_at.is_(None)),
    "payroll_novelties": dict(relations={
        "payroll_novelty_type": Relation("payroll_novelty_types", "payroll_novelty_type_id"),
    }),
    "related_exception_and_payroll_novelty": dict(relations={
        "exception": Relation("exceptions", "exception_id"),
        "payroll_novelty": Relation("payroll_novelties", "payroll_novelty_id"),
    }),
    "silos": dict(relations={
        "silo_type": Relation("silo_types", "silo_type_id"),
        "report_to_silo": Relation("silos", "report_to_silo_id"),
    }),
}


def _default_sort(table: Table) -> str:
    return next(name for name in ("order", "name", "id") if name in table.c)


def _build() -> Dict[str, CatalogSpec]:
    all_tables = [value for value in vars(tables).values() if isinstance(value, Table)]
    catalog_tables = {table.name.removeprefix("general_"): table for table in all_tables}
    assert len(catalog_tables) == len(all_tables), "two tables in tables.py map to the same catalog name"
    catalogs = {
        name: CatalogSpec(table=table, **{"default_sort": _default_sort(table), **_CUSTOM.get(name, {})})
        for name, table in sorted(catalog_tables.items())
    }

    # Fail at startup, not on the first request, if _CUSTOM drifts from the tables.
    for name, spec in catalogs.items():
        for relation_name, relation in spec.relations.items():
            assert relation.catalog in catalogs, f"{name}.{relation_name}: unknown catalog {relation.catalog}"
            assert relation.fk in spec.table.c, f"{name}.{relation_name}: {relation.fk} is not a column"
    assert set(_CUSTOM) <= set(catalogs), f"_CUSTOM has unknown catalogs: {set(_CUSTOM) - set(catalogs)}"
    return catalogs


CATALOGS: Dict[str, CatalogSpec] = _build()
