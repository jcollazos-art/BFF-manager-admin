"""Whole-company employee lists (no person id): manager options, latest positions, salary
increases, monthly headcount and technologies' external ids."""

from datetime import date
from decimal import Decimal

from app.features.catalogs.tables import (
    general_cities,
    general_countries,
    general_document_types,
    general_roles,
    general_silos,
)
from tests.features.catalogs.factories import make_row
from tests.features.employee.factories import (
    make_operational_profile,
    make_person,
    make_position,
    make_role,
    make_technology,
)

BASE = "/v1/employee"


def _get(client, path):
    return client.get(f"{BASE}/{path}").json()["data"]


# --- manager options ------------------------------------------------------------------------


def test_manager_options_need_an_active_position_outside_dedicated_except_kams(client, db):
    account_manager = make_row(db, general_roles, name="Account Manager")
    kam = make_row(db, general_roles, name="Key Account Manager")
    developer = make_row(db, general_roles, name="Developer")
    cloud = make_row(db, general_silos, name="Cloud")
    dedicated = make_row(db, general_silos, name="Dedicated")

    def manager(first_name, role, silo, is_active=True, extra_profiles=0):
        person = make_person(db, first_name=first_name)
        role_row = make_role(db, person, role_id=role["id"], is_main=True)
        profiles = [make_operational_profile(db, role_row) for _ in range(1 + extra_profiles)]
        make_position(db, role_row, silo_id=silo["id"], is_active=is_active)
        return person, profiles

    ana, ana_profiles = manager("Ana", account_manager, cloud, extra_profiles=1)
    bea, bea_profiles = manager("Bea", kam, dedicated)  # KAM: Dedicated silo is fine
    manager("Carl", account_manager, dedicated)  # not a KAM in Dedicated -> out
    manager("Dan", account_manager, cloud, is_active=False)  # no active position -> out
    manager("Eve", developer, cloud)  # not a manager role -> out

    rows = _get(client, "managers/options")

    assert rows == [
        {"id": ana.id, "name": "Ana Gomez", "role": "Account Manager", "profile_ids": sorted(p.id for p in ana_profiles)},
        {"id": bea.id, "name": "Bea Gomez", "role": "Key Account Manager", "profile_ids": [bea_profiles[0].id]},
    ]


# --- latest position ------------------------------------------------------------------------


def test_persons_last_position_with_catalog_names(client, db):
    colombia = make_row(db, general_countries, name="Colombia")
    bogota = make_row(db, general_cities, name="Bogota", country_id=colombia["id"])
    passport = make_row(db, general_document_types, name="Passport")
    person = make_person(db, city_id=bogota["id"], identification_type_id=passport["id"])
    role = make_role(db, person)
    make_position(db, role, effective_date=date(2024, 1, 1), is_active=False, contract_type_id=1)
    latest = make_position(db, make_role(db, person), effective_date=date(2025, 1, 1), contract_type_id=2)
    make_person(db)  # without positions -> out

    (row,) = _get(client, "persons/last-position")

    assert (row["person_id"], row["full_name"], row["city"], row["country"], row["identification_type"]) == (
        person.id, "Ana Gomez", "Bogota", "Colombia", "Passport",
    )
    assert (row["position_id"], row["is_active"], row["contract_type_id"]) == (latest.id, True, 2)


# --- salary increases -----------------------------------------------------------------------


def test_last_salary_increase_is_the_newest_raise(client, db):
    person = make_person(db)
    role = make_role(db, person)
    for effective_date, salary in [(date(2023, 1, 1), 1000), (date(2024, 1, 1), 1500), (date(2025, 1, 1), 1200)]:
        make_position(db, role, effective_date=effective_date, salary=Decimal(salary))
    never_raised = make_person(db)
    make_position(db, make_role(db, never_raised), effective_date=date(2024, 1, 1))

    # 2025 lowered the salary, so the last raise is 2024.
    assert _get(client, "persons/last-salary-increases") == [{"person_id": person.id, "effective_date": "2024-01-01"}]


# --- monthly headcount ----------------------------------------------------------------------


def test_monthly_headcount_counts_employees_with_a_position_in_the_month(client, db):
    ana, bea = make_person(db), make_person(db)
    make_position(db, make_role(db, ana), start_date=date(2025, 11, 20), end_date=date(2026, 1, 5))
    make_position(db, make_role(db, ana), start_date=date(2026, 1, 6), end_date=None)  # same person twice in 2026-01
    make_position(db, make_role(db, bea), start_date=date(2025, 12, 31), end_date=date(2025, 12, 31))

    rows = {row["year_month"]: row for row in _get(client, "headcount/monthly")}

    assert "2025-10" not in rows
    assert (rows["2025-11"]["employees"], rows["2025-11"]["person_ids"]) == (1, [ana.id])
    assert (rows["2025-12"]["employees"], sorted(rows["2025-12"]["person_ids"])) == (2, sorted([ana.id, bea.id]))
    assert rows["2026-01"]["employees"] == 1
    assert rows[date.today().strftime("%Y-%m")]["person_ids"] == [ana.id]  # open position up to today


# --- technologies' external ids -------------------------------------------------------------


def test_technology_external_ids_only_linked_ones(client, db):
    person = make_person(db)
    make_technology(db, person, knowledge_external_id=77, seniority_external_id=3)
    make_technology(db, person, knowledge_external_id=None)

    assert _get(client, "technologies/external-ids") == [
        {"person_id": person.id, "knowledge_external_id": 77, "seniority_external_id": 3},
    ]
