"""POST /<resource>/bulk-upsert: one endpoint creates and/or updates one or many rows.
The rules are the same for every resource (they live in BaseRepository.upsert_many), so the
behaviour is covered in depth on one resource and the per-resource wiring is checked with a
parametrized smoke test."""

from decimal import Decimal

import pytest

from app.features.employee.models import EmployeeLanguage, EmployeePosition, EmployeeRole
from tests.features.employee.factories import make_language, make_person, make_position, make_role

BASE = "/v1/employee"


def _reload(db, model, row_id):
    """Read the row back from the database, not from the session's identity map."""
    db.expunge_all()
    return db.get(model, row_id)


def test_creates_and_updates_in_the_same_call(client, db):
    person = make_person(db)
    existing = make_language(db, person, language_level_id=1)

    body = client.post(f"{BASE}/languages/bulk-upsert", json=[
        {"id": existing.id, "language_level_id": 4},
        {"person_id": person.id, "language_id": 2, "language_level_id": 3},
    ]).json()

    assert body["ok"] is True
    updated, created = body["results"]
    assert updated == {"index": 0, "ok": True, "id": existing.id, "error": None}
    assert _reload(db, EmployeeLanguage, existing.id).language_level_id == 4
    new_row = _reload(db, EmployeeLanguage, created["id"])
    assert (new_row.person_id, new_row.language_id, new_row.language_level_id) == (person.id, 2, 3)


def test_update_only_changes_the_fields_sent(client, db):
    person = make_person(db)
    language = make_language(db, person, language_id=7, language_level_id=1)

    client.post(f"{BASE}/languages/bulk-upsert", json=[{"id": language.id, "language_level_id": 2}])

    row = _reload(db, EmployeeLanguage, language.id)
    assert (row.language_id, row.language_level_id) == (7, 2)


def test_a_single_item_is_a_list_of_one(client, db):
    person = make_person(db)

    body = client.post(f"{BASE}/roles/bulk-upsert", json=[{"person_id": person.id, "role_id": 9}]).json()

    assert body["ok"] is True
    assert _reload(db, EmployeeRole, body["results"][0]["id"]).role_id == 9


def test_failed_items_do_not_block_the_rest(client, db):
    person = make_person(db)

    body = client.post(f"{BASE}/languages/bulk-upsert", json=[
        {"language_id": 1},                       # create without parent
        {"id": 999999, "language_id": 1},         # update of a row that doesn't exist
        {"person_id": person.id, "language_id": 1},
    ]).json()

    assert body["ok"] is False
    missing_parent, missing_row, created = body["results"]
    assert "requires person_id" in missing_parent["error"]
    assert "id 999999 not found" in missing_row["error"]
    assert created["ok"] is True and _reload(db, EmployeeLanguage, created["id"]) is not None


def test_database_error_rolls_back_only_that_item(client, db):
    # A real constraint violation (FK to a person that doesn't exist) inside the batch: the
    # per-item SAVEPOINT must leave the transaction usable for the next items.
    person = make_person(db)

    body = client.post(f"{BASE}/roles/bulk-upsert", json=[
        {"person_id": 999999, "role_id": 1},
        {"person_id": person.id, "role_id": 2},
    ]).json()

    failed, created = body["results"]
    assert failed["ok"] is False and "foreign key" in failed["error"].lower()
    assert created["ok"] is True and _reload(db, EmployeeRole, created["id"]).role_id == 2


def test_decimal_values_round_trip_exactly(client, db):
    role = make_role(db, make_person(db))
    position = make_position(db, role)

    client.post(f"{BASE}/positions/bulk-upsert", json=[{"id": position.id, "salary": 6114.78, "bonus": 0.125}])

    row = _reload(db, EmployeePosition, position.id)
    assert row.salary == Decimal("6114.78") and row.bonus == Decimal("0.125")


def test_invalid_payload_is_rejected_before_writing(client):
    response = client.post(f"{BASE}/languages/bulk-upsert", json={"person_id": 1})  # not a list

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


@pytest.mark.parametrize(
    ("resource", "parent_field"),
    [
        ("persons", "first_name, last_name"),
        ("roles", "person_id"),
        ("operational-profiles", "employee_role_id"),
        ("positions", "employee_role_id"),
        ("assignations", "operational_profile_id"),
        ("technologies", "person_id"),
        ("languages", "person_id"),
        ("equipments", "person_id"),
    ],
)
def test_every_resource_requires_its_parent_to_create(client, resource, parent_field):
    body = client.post(f"{BASE}/{resource}/bulk-upsert", json=[{}]).json()

    assert body["results"][0]["error"].endswith(f"requires {parent_field} to be created")
