"""Builders for dashboard scenarios, on top of the employee/catalog/company factories."""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.features.catalogs.tables import bill_exchange
from app.features.companies.models import CompanyAccount
from app.features.employee.models import (
    EmployeeOperationalProfile,
    EmployeePerson,
    EmployeePosition,
    EmployeeRole,
    OperationAssignation,
)
from tests.features.catalogs.factories import make_row
from tests.features.employee.factories import (
    make_assignation,
    make_operational_profile,
    make_person,
    make_position,
    make_role,
)


@dataclass
class Employee:
    person: EmployeePerson
    role: EmployeeRole
    profile: EmployeeOperationalProfile
    position: EmployeePosition
    assignation: OperationAssignation


def make_employee(
    db: Session,
    account: CompanyAccount,
    *,
    person: Optional[dict] = None,
    role: Optional[dict] = None,
    profile: Optional[dict] = None,
    position: Optional[dict] = None,
    assignation: Optional[dict] = None,
) -> Employee:
    """Person -> role -> profile + position + assignation on `account`. The position starts
    2025-01-01 and is open; the assignation starts 2025-02-01, is open and billable."""
    person_row = make_person(db, **(person or {}))
    role_row = make_role(db, person_row, **(role or {}))
    profile_row = make_operational_profile(db, role_row, **(profile or {}))
    position_row = make_position(
        db, role_row, **{"start_date": date(2025, 1, 1), "effective_date": date(2025, 1, 1), **(position or {})}
    )
    assignation_row = make_assignation(
        db,
        profile_row,
        **{
            "account_id": account.id,
            "start_date": date(2025, 2, 1),
            "effective_date": date(2025, 2, 1),
            "monthly_sales_price": Decimal("1000"),
            **(assignation or {}),
        },
    )
    return Employee(person_row, role_row, profile_row, position_row, assignation_row)


def add_assignation(db: Session, employee: Employee, account: CompanyAccount, **overrides) -> OperationAssignation:
    fields = {
        "account_id": account.id,
        "start_date": date(2025, 2, 1),
        "effective_date": date(2025, 2, 1),
        "monthly_sales_price": Decimal("1000"),
        **overrides,
    }
    return make_assignation(db, employee.profile, **fields)


def make_exchange_rate(db: Session, nominal: str = "3800", real: str = "4000") -> dict:
    """Factor nominal / real = 0.95 by default."""
    return make_row(db, bill_exchange, nominal=float(nominal), real=float(real), created_at=datetime(2026, 1, 1))
