"""GET /persons/{id}/positions: positions table of the employee's main view, built by
EmployeeRepository.get_person_positions with every catalog id resolved to its name."""

from decimal import Decimal

from app.features.catalogs.tables import (
    general_contract_types,
    general_cost_centers,
    general_roles,
    general_seniorities,
    general_silos,
)
from tests.features.catalogs.factories import make_row
from tests.features.employee.factories import make_person, make_position, make_role

BASE = "/v1/employee"


def _positions(client, person_id):
    return client.get(f"{BASE}/persons/{person_id}/positions").json()["data"]


def test_resolves_every_catalog_name(client, db):
    backend = make_row(db, general_roles, name="Backend")
    senior = make_row(db, general_seniorities, name="Senior")
    contractor = make_row(db, general_contract_types, name="Contractor", currency="USD")
    cost_center = make_row(db, general_cost_centers, name="Delivery")
    silo = make_row(db, general_silos, name="Agile")
    role = make_role(db, make_person(db), role_id=backend["id"], seniority_id=senior["id"])
    position = make_position(
        db, role, contract_type_id=contractor["id"], cost_center_id=cost_center["id"], silo_id=silo["id"],
        salary=Decimal("6114.78"), bonus=Decimal("0.125"),
    )

    (row,) = _positions(client, role.person_id)

    assert row["id"] == position.id
    assert (row["employee_role"], row["seniority"]) == ("Backend", "Senior")
    assert (row["contract_type"], row["cost_center"], row["silo"]) == ("Contractor", "Delivery", "Agile")
    assert (row["salary"], row["bonus"]) == (6114.78, 0.125)


def test_active_first_then_newest_and_unknown_status_last(client, db):
    person = make_person(db)
    role = make_role(db, person)
    other_role = make_role(db, person, is_main=False)
    old_active = make_position(db, role, is_active=True)
    unknown = make_position(db, role, is_active=None)
    inactive = make_position(db, other_role, is_active=False)
    new_active = make_position(db, other_role, is_active=True)

    ids = [row["id"] for row in _positions(client, person.id)]

    assert ids == [new_active.id, old_active.id, inactive.id, unknown.id]


def test_only_returns_this_persons_positions(client, db):
    person = make_person(db)
    make_position(db, make_role(db, make_person(db)))

    assert _positions(client, person.id) == []
