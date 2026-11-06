"""GET /persons/{id}/technologies: technologies table of the employee's main view, built by
EmployeeRepository.get_person_technologies with the seniority name resolved."""

from app.features.catalogs.tables import general_seniorities
from tests.features.catalogs.factories import make_row
from tests.features.employee.factories import make_person, make_technology

BASE = "/v1/employee"


def _technologies(client, person_id):
    return client.get(f"{BASE}/persons/{person_id}/technologies").json()["data"]


def test_resolves_seniority_name_and_score(client, db):
    senior = make_row(db, general_seniorities, name="Senior", order=3)
    person = make_person(db)
    tech = make_technology(
        db, person, knowledge_external_id=42, seniority_external_id=senior["id"], is_principal=True, is_verified=True
    )

    (row,) = _technologies(client, person.id)

    assert row == {
        "id": tech.id,
        "person_id": person.id,
        "knowledge_external_id": 42,
        "seniority_external_id": senior["id"],
        "is_principal": True,
        "is_verified": True,
        "seniority": "Senior",
        "score": 3,
    }


def test_keeps_technologies_without_a_known_seniority(client, db):
    person = make_person(db)
    make_technology(db, person, seniority_external_id=None)
    make_technology(db, person, seniority_external_id=999_999)

    rows = _technologies(client, person.id)

    assert [row["seniority"] for row in rows] == [None, None]


def test_principal_first_then_by_id_and_unknown_last(client, db):
    person = make_person(db)
    unknown = make_technology(db, person, is_principal=None)
    secondary = make_technology(db, person, is_principal=False)
    principal = make_technology(db, person, is_principal=True)

    ids = [row["id"] for row in _technologies(client, person.id)]

    assert ids == [principal.id, secondary.id, unknown.id]


def test_only_returns_this_persons_technologies(client, db):
    person = make_person(db)
    make_technology(db, make_person(db))

    assert _technologies(client, person.id) == []
