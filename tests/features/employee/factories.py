"""Test data builders: each one inserts a valid row with sensible defaults and returns it.
Pass only what the test cares about - `make_person(db, first_name="Ana")` - so each test
reads as the scenario it checks."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.features.employee.models import (
    EmployeeEquipment,
    EmployeeLanguage,
    EmployeeOperationalProfile,
    EmployeePerson,
    EmployeePosition,
    EmployeeRole,
    EmployeeTechnology,
    GeneralCity,
    OperationAssignation,
)


def _insert(db: Session, row):
    now = datetime(2026, 1, 1)
    row.created_at = row.created_at or now
    row.updated_at = row.updated_at or now
    db.add(row)
    db.flush()
    return row


def make_city(db: Session, **overrides) -> GeneralCity:
    db.add(city := GeneralCity(**{"country_id": 1, **overrides}))
    db.flush()
    return city


def make_person(db: Session, **overrides) -> EmployeePerson:
    fields = {"first_name": "Ana", "last_name": "Gomez", "identification": "100200300", **overrides}
    return _insert(db, EmployeePerson(**fields))


def make_role(db: Session, person: EmployeePerson, **overrides) -> EmployeeRole:
    fields = {"person_id": person.id, "role_id": 78, "seniority_id": 4, "is_main": True, **overrides}
    return _insert(db, EmployeeRole(**fields))


def make_operational_profile(db: Session, role: EmployeeRole, **overrides) -> EmployeeOperationalProfile:
    fields = {"employee_role_id": role.id, "is_certified": False, "is_available": True, **overrides}
    return _insert(db, EmployeeOperationalProfile(**fields))


def make_position(db: Session, role: EmployeeRole, **overrides) -> EmployeePosition:
    fields = {
        "employee_role_id": role.id,
        "currency": "USD",
        "salary": Decimal("5000.00"),
        "is_active": True,
        "start_date": date(2025, 1, 1),
        **overrides,
    }
    return _insert(db, EmployeePosition(**fields))


def make_assignation(db: Session, profile: EmployeeOperationalProfile, **overrides) -> OperationAssignation:
    fields = {
        "operational_profile_id": profile.id,
        "account_id": 215,
        "allocation": Decimal("1.00"),
        "is_billable": True,
        "monthly_sales_price": Decimal("6114.78"),
        "start_date": date(2025, 1, 1),
        **overrides,
    }
    return _insert(db, OperationAssignation(**fields))


def make_technology(db: Session, person: EmployeePerson, **overrides) -> EmployeeTechnology:
    fields = {"person_id": person.id, "technology_id": 1, "seniority_id": 2, "is_principal": False, **overrides}
    return _insert(db, EmployeeTechnology(**fields))


def make_language(db: Session, person: EmployeePerson, **overrides) -> EmployeeLanguage:
    fields = {"person_id": person.id, "language_id": 1, "language_level_id": 1, **overrides}
    return _insert(db, EmployeeLanguage(**fields))


def make_equipment(db: Session, person: EmployeePerson, **overrides) -> EmployeeEquipment:
    return _insert(db, EmployeeEquipment(**{"person_id": person.id, "hardware_id": 1, **overrides}))


def make_full_employee(db: Session) -> EmployeePerson:
    """A person with one of everything - for tests about the nested detail view."""
    person = make_person(db, city_id=make_city(db, country_id=57).id)
    role = make_role(db, person)
    profile = make_operational_profile(db, role)
    make_position(db, role)
    make_assignation(db, profile)
    make_technology(db, person)
    make_language(db, person)
    make_equipment(db, person)
    return person
