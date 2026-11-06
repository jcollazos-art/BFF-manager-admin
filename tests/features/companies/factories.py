from datetime import datetime

from sqlalchemy.orm import Session

from app.features.companies.models import CompanyAccount, TechnologyAccount


def _insert(db: Session, row):
    row.created_at = row.created_at or datetime(2026, 1, 1)
    row.updated_at = row.updated_at or datetime(2026, 1, 1)
    db.add(row)
    db.flush()
    return row


def make_account(db: Session, **overrides) -> CompanyAccount:
    return _insert(db, CompanyAccount(**{"name": "Acme", **overrides}))


def make_technology_account(db: Session, account: CompanyAccount, technology_id: int, **overrides) -> TechnologyAccount:
    fields = {"account_id": account.id, "technology_id": technology_id, **overrides}
    return _insert(db, TechnologyAccount(**fields))
