"""GET /persons/{id}/technology-experience, built by sql/person_technology_experience.sql."""

from datetime import date

from app.features.catalogs.tables import general_seniorities, general_technology_categories, technologies
from tests.features.catalogs.factories import make_row
from tests.features.companies.factories import make_account, make_technology_account
from tests.features.employee.factories import make_assignation, make_operational_profile, make_person, make_role, make_technology

BASE = "/v1/employee"


def _experience(client, person_id):
    return client.get(f"{BASE}/persons/{person_id}/technology-experience").json()["data"]


def test_experience_per_account_is_its_longest_assignation(client, db):
    backend = make_row(db, general_technology_categories, name="Backend")
    python = make_row(db, technologies, name="Python", category_id=backend["id"])
    senior = make_row(db, general_seniorities, name="Senior", order=3)
    account = make_account(db, name="Acme")
    make_technology_account(db, account, python["id"])
    person = make_person(db)
    profile = make_operational_profile(db, make_role(db, person))
    make_assignation(db, profile, account_id=account.id, start_date=date(2023, 1, 1), end_date=date(2023, 12, 31))
    make_assignation(db, profile, account_id=account.id, start_date=date(2024, 1, 1), end_date=date(2024, 1, 31))
    make_technology(db, person, technology_id=python["id"], seniority_id=senior["id"])

    (row,) = _experience(client, person.id)

    assert row == {
        "person_id": person.id,
        "technology_id": python["id"],
        "technology": "Python",
        "type": "Backend",
        "seniority": "Senior",
        "exp_in_days": 364,
        "exp_in_year": 0.9,
        "account_id": account.id,
        "account": "Acme",
    }


def test_technology_without_account_experience_is_one_row_with_nulls(client, db):
    python = make_row(db, technologies, name="Python")
    person = make_person(db)
    make_technology(db, person, technology_id=python["id"], seniority_id=None)

    (row,) = _experience(client, person.id)

    assert (row["technology"], row["seniority"], row["account_id"], row["exp_in_days"], row["exp_in_year"]) == (
        "Python", None, None, None, 0.0,
    )


def test_not_repeated_per_role(client, db):
    # Retool joined employee_roles and returned each technology once per role.
    python = make_row(db, technologies, name="Python")
    person = make_person(db)
    make_role(db, person)
    make_role(db, person, is_main=False)
    make_technology(db, person, technology_id=python["id"])

    assert len(_experience(client, person.id)) == 1
