"""GET /persons/{id}/assignations: each assignation paired with the positions it overlaps,
built by sql/person_assignations.sql."""

from datetime import date
from decimal import Decimal

import pytest

from app.features.catalogs.tables import general_cost_centers, general_profit_and_loss
from tests.features.catalogs.factories import make_row
from tests.features.companies.factories import make_account
from tests.features.employee.factories import (
    make_assigned_employee,
    make_operational_profile,
    make_person,
    make_position,
    make_role,
)

BASE = "/v1/employee"


def _assignations(client, person_id):
    return client.get(f"{BASE}/persons/{person_id}/assignations").json()["data"]


def test_pairs_with_overlapping_position_and_computes_margin(client, db):
    account = make_account(db, name="Acme")
    pnl = make_row(db, general_profit_and_loss, name="Delivery P&L")
    cost_center = make_row(db, general_cost_centers, name="Delivery", profit_loss_id=pnl["id"])
    person, role, assignation = make_assigned_employee(
        db, account_id=account.id, cost_center_id=cost_center["id"], effective_date=date(2025, 1, 1),
        allocation=Decimal("0.50"), monthly_sales_price=Decimal("8000.00"), is_billable=True,
    )
    position = make_position(db, role, effective_date=date(2024, 6, 1), cost=Decimal("3000.00"))

    (row,) = _assignations(client, person.id)

    assert (row["assignation_id"], row["position_id"]) == (assignation.id, position.id)
    assert (row["account"], row["cost_center"], row["p_l_category"]) == ("Acme", "Delivery", "Delivery P&L")
    assert row["sales_price"] == 4000.0
    assert row["employee_cost"] == 3000.0
    assert row["margin"] == pytest.approx(0.25)
    assert row["is_active"] is True


def test_non_billable_margin_is_zero(client, db):
    person, role, _ = make_assigned_employee(db, effective_date=date(2025, 1, 1), is_billable=False)
    make_position(db, role, effective_date=date(2025, 1, 1), cost=Decimal("3000.00"))

    (row,) = _assignations(client, person.id)

    assert row["margin"] == 0


@pytest.mark.parametrize(
    "position_range, overlaps",
    [
        ((date(2024, 1, 1), date(2024, 12, 31)), False),  # ends the day before the assignation
        ((date(2024, 1, 1), date(2025, 1, 1)), True),  # ends the day it starts (inclusive)
        ((date(2025, 3, 1), date(2025, 4, 1)), True),  # inside the assignation
        ((date(2025, 6, 1), None), True),  # open position starting inside it
        ((date(2025, 7, 1), None), False),  # starts after the assignation ended
    ],
)
def test_only_pairs_positions_overlapping_in_time(client, db, position_range, overlaps):
    person, role, _ = make_assigned_employee(db, effective_date=date(2025, 1, 1), end_date=date(2025, 6, 30))
    make_position(db, role, effective_date=position_range[0], end_date=position_range[1])

    assert len(_assignations(client, person.id)) == (1 if overlaps else 0)


def test_missing_catalogs_dont_drop_the_assignation(client, db):
    # Retool's INNER JOINs dropped this one: unknown account and cost center.
    person, role, _ = make_assigned_employee(db, account_id=999_999, cost_center_id=None, effective_date=date(2025, 1, 1))
    make_position(db, role, effective_date=date(2025, 1, 1))

    (row,) = _assignations(client, person.id)

    assert (row["account"], row["cost_center"], row["manager"]) == (None, None, None)


def test_resolves_the_account_manager_through_its_operational_profile(client, db):
    manager_profile = make_operational_profile(db, make_role(db, make_person(db, first_name="Laura", last_name="Diaz")))
    account = make_account(db, manager_id=manager_profile.id)
    person, role, _ = make_assigned_employee(db, account_id=account.id, effective_date=date(2025, 1, 1))
    make_position(db, role, effective_date=date(2025, 1, 1))

    (row,) = _assignations(client, person.id)

    assert (row["manager_id"], row["manager"]) == (manager_profile.id, "Laura Diaz")


def test_ignores_soft_deleted_positions_and_other_people(client, db):
    person, role, _ = make_assigned_employee(db, effective_date=date(2025, 1, 1))
    make_position(db, role, effective_date=date(2025, 1, 1), deleted_at=date(2025, 2, 1))
    other, other_role, _ = make_assigned_employee(db, effective_date=date(2025, 1, 1))
    make_position(db, other_role, effective_date=date(2025, 1, 1))

    assert _assignations(client, person.id) == []


def test_active_positions_first(client, db):
    person, role, _ = make_assigned_employee(db, effective_date=date(2024, 1, 1))
    ended = make_position(db, role, effective_date=date(2024, 1, 1), end_date=date(2024, 12, 31))
    open_ = make_position(db, role, effective_date=date(2025, 1, 1))

    rows = _assignations(client, person.id)

    assert [(row["position_id"], row["is_active"]) for row in rows] == [(open_.id, True), (ended.id, False)]
