"""Catalogs are Core tables, so one builder covers all of them:
`make_row(db, general_cities, name="Bogota", country_id=colombia["id"])`."""

from datetime import datetime

from sqlalchemy import Table
from sqlalchemy.orm import Session


def make_row(db: Session, table: Table, **fields) -> dict:
    if "created_at" in table.c:
        fields = {"created_at": datetime(2026, 1, 1), "updated_at": datetime(2026, 1, 1), **fields}
    row_id = db.execute(table.insert().values(**fields).returning(table.c.id)).scalar_one()
    return {"id": row_id, **fields}
