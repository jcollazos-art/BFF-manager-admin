from datetime import datetime

from sqlalchemy.orm import Session

from app.features.companies.models import (
    AccountPoc,
    CompanyAccount,
    CompanyPoc,
    CompanyTeam,
    TechnologyAccount,
    general_persons,
)
from tests.features.catalogs.factories import make_row


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


def make_team(db: Session, account: CompanyAccount, **overrides) -> CompanyTeam:
    return _insert(db, CompanyTeam(**{"name": "Core", "account_id": account.id, **overrides}))


def make_account_poc(db: Session, account: CompanyAccount, *, person: dict = None, **overrides) -> AccountPoc:
    """general.persons row -> company_pocs -> account_pocs on `account`, active by default."""
    person_row = make_row(db, general_persons, **{"first_name": "Laura", "last_name": "Diaz", **(person or {})})
    company_poc = _insert(db, CompanyPoc(external_person_id=person_row["id"], is_active=True))
    return _insert(db, AccountPoc(**{"company_poc_id": company_poc.id, "account_id": account.id, "is_active": True, **overrides}))
