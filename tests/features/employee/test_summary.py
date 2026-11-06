"""GET /persons/{id}/summary: the employee's main-view header, built by
sql/person_summary.sql with every catalog id resolved to its name."""

from datetime import date

from app.features.catalogs.tables import (
    general_cities,
    general_countries,
    general_document_types,
    general_languages,
    general_roles,
    general_seniorities,
    technologies,
)
from tests.features.catalogs.factories import make_row
from tests.features.employee.factories import make_language, make_person, make_role, make_technology

BASE = "/v1/employee"


def _summary(client, person_id):
    return client.get(f"{BASE}/persons/{person_id}/summary")


def test_resolves_every_catalog_name(client, db):
    colombia = make_row(db, general_countries, name="Colombia")
    peru = make_row(db, general_countries, name="Peru")
    bogota = make_row(db, general_cities, name="Bogota", country_id=colombia["id"])
    passport = make_row(db, general_document_types, name="Passport")
    person = make_person(
        db, first_name="Ana", last_name="Gomez", birth_date=date(1990, 5, 1),
        city_id=bogota["id"], nationality_id=peru["id"], identification_type_id=passport["id"],
    )

    data = _summary(client, person.id).json()["data"]

    assert data["employee_id"] == person.id
    assert data["fullname"] == "Ana Gomez"
    assert (data["city"], data["country"], data["nationality"]) == ("Bogota", "Colombia", "Peru")
    assert data["identification_type"] == "Passport"
    assert data["birth_date"] == "1990-05-01"


def test_roles_come_as_a_list_with_the_main_one_first(client, db):
    backend = make_row(db, general_roles, name="Backend")
    qa = make_row(db, general_roles, name="QA")
    senior = make_row(db, general_seniorities, name="Senior")
    person = make_person(db)
    secondary = make_role(db, person, role_id=qa["id"], seniority_id=None, is_main=False)
    main = make_role(db, person, role_id=backend["id"], seniority_id=senior["id"], is_main=True)

    roles = _summary(client, person.id).json()["data"]["roles"]

    assert roles == [
        {"id": main.id, "role": "Backend", "seniority": "Senior", "is_main": True},
        {"id": secondary.id, "role": "QA", "seniority": None, "is_main": False},
    ]


def test_tech_and_language_stacks(client, db):
    python = make_row(db, technologies, name="Python")
    go = make_row(db, technologies, name="Go")
    english = make_row(db, general_languages, name="English")
    spanish = make_row(db, general_languages, name="Spanish")
    person = make_person(db)
    make_technology(db, person, technology_id=go["id"], is_principal=False)
    make_technology(db, person, technology_id=python["id"], is_principal=True)
    make_technology(db, person, technology_id=999999)  # orphan id: ignored, like in Retool
    make_language(db, person, language_id=spanish["id"])
    make_language(db, person, language_id=english["id"])
    other = make_person(db)
    make_technology(db, other, technology_id=go["id"])  # another person's data never leaks in

    data = _summary(client, person.id).json()["data"]

    assert data["main_tech"] == "Python"
    assert data["tech_stack"] == "Python, Go"
    assert data["language_stack"] == "English, Spanish"


def test_person_without_roles_or_skills_is_still_returned(client, db):
    # Retool's INNER JOINs returned nothing for this person.
    person = make_person(db, first_name="Solo", last_name=None)

    data = _summary(client, person.id).json()["data"]

    assert data["fullname"] == "Solo"
    assert data["roles"] == []
    assert (data["tech_stack"], data["main_tech"], data["language_stack"]) == (None, None, None)


def test_unknown_person_is_404(client):
    response = _summary(client, 999999)

    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"
