"""Employees dashboard (GET /employee/dashboard/*): one scenario per endpoint, checking the
business rule it implements and the Retool bug it fixes."""

from datetime import date, datetime, timedelta
from decimal import Decimal

from app.features.catalogs.tables import (
    general_cost_centers,
    general_cycles,
    general_governance_concepts,
    general_language_levels,
    general_languages,
    general_profit_and_loss,
    general_reasons,
    general_roles,
    general_seniorities,
    general_silos,
    technologies,
)
from app.features.employee.models import pcu_responses
from app.features.employee_dashboard.models import (
    bill_employee_history,
    cost_employee_history,
    governance_models,
    operation_resource_releases,
)
from tests.features.catalogs.factories import make_row
from tests.features.companies.factories import make_account
from tests.features.employee.factories import (
    make_language,
    make_operational_profile,
    make_person,
    make_position,
    make_role,
    make_technology,
)
from tests.features.employee_dashboard.factories import add_assignation, make_employee, make_exchange_rate

BASE = "/v1/employee/dashboard"


def _get(client, path, **params):
    response = client.get(f"{BASE}/{path}", params=params)
    assert response.status_code == 200, response.json()
    return response.json()["data"]


# --- distributions --------------------------------------------------------------------------


def test_english_levels_count_employees_not_assignations(client, db):
    english = make_row(db, general_languages, name="English")
    advanced = make_row(db, general_language_levels, name="Advanced")
    backend = make_row(db, general_roles, name="Backend")
    acme = make_account(db)
    ana = make_employee(db, acme, role={"role_id": backend["id"]})
    add_assignation(db, ana, acme)  # second assignation: Retool counted Ana twice
    make_language(db, ana.person, language_id=english["id"], language_level_id=advanced["id"])
    make_employee(db, acme)  # no English -> Others
    make_employee(  # position ended -> not active
        db, acme, position={"end_date": date(2025, 6, 1)}, assignation={"end_date": date(2025, 5, 1)}
    )

    assert _get(client, "english-levels") == [
        {"english_level": "Advanced", "employees": 1},
        {"english_level": "Others", "employees": 1},
    ]
    assert _get(client, "english-levels", role_ids=[backend["id"]]) == [{"english_level": "Advanced", "employees": 1}]
    assert _get(client, "english-levels", employees="all") == [
        {"english_level": "Others", "employees": 2},
        {"english_level": "Advanced", "employees": 1},
    ]


def test_seniorities_and_main_technologies(client, db):
    senior = make_row(db, general_seniorities, name="Senior", order=3)
    python = make_row(db, technologies, name="Python")
    acme = make_account(db)
    ana = make_employee(db, acme, role={"seniority_id": senior["id"]}, profile={"is_available": True})
    bea = make_employee(db, acme, role={"seniority_id": senior["id"]}, profile={"is_available": False})
    for employee in (ana, bea):
        make_technology(db, employee.person, technology_id=python["id"], is_principal=True)

    assert _get(client, "seniorities") == [{"seniority": "Senior", "employees": 2}]
    assert _get(client, "main-technologies") == [{"main_tech": "Python", "employees": 2}]
    assert _get(client, "main-technologies", availability="available") == [{"main_tech": "Python", "employees": 1}]


# --- monthly KPIs ---------------------------------------------------------------------------


def test_financials_of_the_month(client, db):
    backend = make_row(db, general_roles, name="Backend")
    october = make_row(db, general_cycles, name="2026-10", start_date=date(2026, 10, 1))
    acme, beta = make_account(db, name="Acme"), make_account(db, name="Beta")
    ana = make_employee(db, acme, role={"role_id": backend["id"]})
    on_beta = add_assignation(db, ana, beta)
    for assignation, account, price in ((ana.assignation, acme, 1000), (on_beta, beta, 2000)):
        common = dict(person_id=ana.person.id, account_id=account.id, cycle_id=october["id"])
        make_row(db, bill_employee_history, assignation_id=assignation.id, monthly_sales_price=Decimal(price), **common)
        make_row(db, cost_employee_history, real_cost=Decimal(600), cost=Decimal(500), **common)

    data = _get(client, "financials", month="2026-10")

    assert (data["revenue"], data["profit"], data["real_cost"], data["cost"]) == (3000, 1800, 1200, 1000)
    assert data["margin"] == 0.6
    # role_ids are general_roles ids (Retool compared them with employee_role ids)
    assert _get(client, "financials", month="2026-10", role_ids=[backend["id"]])["revenue"] == 3000
    assert _get(client, "financials", month="2026-10", role_ids=[ana.role.id + 1000])["revenue"] is None


def test_financials_rejects_a_malformed_month(client):
    assert client.get(f"{BASE}/financials", params={"month": "2026-13"}).status_code == 422


def test_cost_totals_count_each_history_row_once(client, db):
    person = make_person(db)
    make_role(db, person)
    make_role(db, person)  # Retool summed the cost once per role
    make_row(db, cost_employee_history, person_id=person.id, real_cost=Decimal(100), cost=Decimal(50))
    make_row(db, cost_employee_history, person_id=person.id, real_cost=Decimal(300), cost=None)

    assert _get(client, "cost-totals") == {"real_cost": 400, "avg_real_cost": 200, "cost": 50, "avg_cost": 25}


def test_new_assignations_booking_vs_billable(client, db):
    lss = make_row(db, general_profit_and_loss, name="Dedicated-LSS")
    lss_center = make_row(db, general_cost_centers, name="LSS", profit_loss_id=lss["id"])
    acme = make_account(db, billing_cycle=15)

    def new(start, **overrides):
        make_employee(db, acme, assignation={"start_date": start, "effective_date": start, **overrides})

    new(date(2026, 10, 20))  # after the cycle day -> booking
    new(date(2026, 10, 5))  # no cost center: Retool's `<> 'Dedicated-LSS'` dropped it
    new(date(2026, 10, 6), cost_center_id=lss_center["id"])  # LSS: only with include_lss
    new(date(2026, 9, 20))  # other month
    new(date(2026, 10, 7), is_billable=False)
    make_employee(db, acme, assignation={"start_date": date(2026, 1, 1), "effective_date": date(2026, 10, 8)})

    assert _get(client, "new-assignations", month="2026-10") == {"total_booking": 1, "total_billable": 1}
    assert _get(client, "new-assignations", month="2026-10", include_lss=True)["total_billable"] == 2


def test_leaving_counts_offboarded_employees(client, db):
    offboarding = make_row(db, general_reasons, name="Offboarding")
    other = make_row(db, general_reasons, name="Promotion")
    acme, beta = make_account(db), make_account(db)
    ana = make_employee(db, acme, assignation={"end_date": date(2026, 10, 15), "end_reason_id": offboarding["id"]})
    add_assignation(db, ana, beta, end_date=date(2026, 10, 20), end_reason_id=offboarding["id"])  # same person
    make_employee(db, acme, assignation={"end_date": date(2026, 10, 15), "end_reason_id": other["id"]})

    assert _get(client, "leaving", month="2026-10") == {"total_leaving": 1}


# --- headcount ------------------------------------------------------------------------------


def test_headcount_per_month_with_billables(client, db):
    acme = make_account(db)
    make_employee(
        db, acme,
        position={"start_date": date(2026, 9, 15), "effective_date": date(2026, 9, 15), "end_date": date(2026, 10, 10)},
        assignation={"effective_date": date(2026, 9, 15)},
    )
    make_employee(
        db, acme,
        position={"start_date": date(2026, 10, 1), "effective_date": date(2026, 10, 1), "end_date": date(2026, 10, 31)},
        assignation={"effective_date": date(2026, 10, 1), "is_billable": False},
    )

    rows = {row["year_month"]: row for row in _get(client, "headcount", employees="all")}

    assert rows["2019-05"] == {"year_month": "2019-05", "employees": 0, "billables": 0}
    assert rows["2026-09"] == {"year_month": "2026-09", "employees": 1, "billables": 1}
    assert rows["2026-10"] == {"year_month": "2026-10", "employees": 2, "billables": 1}
    assert rows["2026-11"]["employees"] == 0
    # employees=active (default) means positions without end_date
    assert all(row["employees"] == 0 for row in _get(client, "headcount"))


# --- tables ---------------------------------------------------------------------------------


def test_employees_one_row_per_employee_with_their_assignations(client, db):
    make_exchange_rate(db)  # factor 0.95
    manager = make_person(db, first_name="Mia", corporate_email="mia@lean.io")
    manager_profile = make_operational_profile(db, make_role(db, manager))
    acme = make_account(db, name="Acme")
    beta = make_account(db, name="Beta", manager_id=manager_profile.id)
    ana = make_employee(
        db, acme,
        person={"corporate_email": "ana@lean.io"},
        position={"currency": "COP", "cost": Decimal("1000000")},
        assignation={"allocation": Decimal("0.5")},
    )
    on_beta = add_assignation(db, ana, beta, monthly_sales_price=Decimal("2000"))
    make_row(db, operation_resource_releases, assignation_id=on_beta.id, is_replaced=True)

    rows = _get(client, "employees")

    ana_row = next(row for row in rows if row["id"] == ana.person.id)
    assert [item["account"] for item in ana_row["assignations"]] == ["Acme", "Beta"]
    assert (ana_row["count_assignations"], ana_row["sales_prices"], ana_row["allocations"]) == (2, 2500, 1.5)
    assert ana_row["employee_cost"] == 950000
    # reason / account manager / profile come from the newest assignation (Beta)
    assert (ana_row["assignation_id"], ana_row["account_manager_name"], ana_row["manager"]) == (
        on_beta.id, "Mia Gomez", "Mia Gomez",
    )
    assert ana_row["is_replaced"] is True
    assert ana_row["pcu_id"] is None and ana_row["employee_quality_id"] is None
    assert len([row for row in rows if row["id"] == ana.person.id]) == 1


def test_employees_without_exchange_rate_is_a_clear_error(client, db):
    response = client.get(f"{BASE}/employees")

    assert response.status_code == 500
    assert response.json()["code"] == "MISSING_EXCHANGE_RATE"


def test_assignations_pair_only_overlapping_positions(client, db):
    make_exchange_rate(db)
    acme = make_account(db)
    ana = make_employee(
        db, acme,
        position={"start_date": date(2024, 1, 1), "effective_date": date(2024, 1, 1), "end_date": date(2024, 12, 31)},
        assignation={"start_date": date(2024, 3, 1), "effective_date": date(2024, 3, 1), "end_date": date(2024, 11, 30)},
    )
    current_position = make_position(db, ana.role, start_date=date(2025, 1, 1), effective_date=date(2025, 1, 1))
    current = add_assignation(db, ana, acme)
    make_row(db, pcu_responses, assignation_id=current.id, report_date=date.today() - timedelta(days=3),
             is_visible_to_customers=False, created_at=datetime(2026, 1, 1), updated_at=datetime(2026, 1, 1))

    rows = _get(client, "assignations", employees="all")

    # Retool: 2 positions x 2 assignations = 4 rows
    assert sorted((row["employee_position_id"], row["assignation_id"]) for row in rows) == sorted([
        (ana.position.id, ana.assignation.id), (current_position.id, current.id),
    ])
    assert {row["assignation_id"]: row["has_pcu"] for row in rows} == {ana.assignation.id: False, current.id: True}


def test_monthly_pl_profit_next_sale_price_and_manager(client, db):
    make_exchange_rate(db)  # factor 0.95
    annual_increase = make_row(db, general_governance_concepts, name="Anual Increase")
    silo_boss = make_person(db, first_name="Leo", corporate_email="leo@lean.io")
    silo = make_row(db, general_silos, name="Cloud", manager_id=make_operational_profile(db, make_role(db, silo_boss)).id)
    acme = make_account(db, name="Acme")
    make_row(db, governance_models, account_id=acme.id, concept_id=annual_increase["id"], value="5%")
    ana = make_employee(
        db, acme,
        person={"corporate_email": "ana@lean.io"},
        position={"currency": "COP", "cost": Decimal("100"), "silo_id": silo["id"]},
        assignation={"start_date": date(2025, 1, 1), "effective_date": date(2025, 1, 1)},
    )
    make_employee(db, acme, assignation={"end_date": date(2026, 9, 30)})  # ended before the month

    (row,) = _get(client, "monthly-pl", month="2026-10")

    assert (row["assignation_id"], row["position_id"]) == (ana.assignation.id, ana.position.id)
    assert (row["employee_cost"], row["profit"]) == (95, 905)  # COP cost converted
    assert (row["next_sale_price"], row["next_sale_price_caption"]) == (1050, "5.0% annual increase")
    assert row["next_sale_price_date"] == "2026-01-01"  # a year after the start, no increase since
    assert row["manager"] == "Leo Gomez"  # no account manager -> silo manager
