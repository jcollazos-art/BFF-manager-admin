"""The ORM-built tables of the employee's main view (GET /persons/{id}/<table>)."""

from datetime import date, datetime, timedelta
from decimal import Decimal

from app.features.catalogs.tables import (
    general_action_statuses,
    general_actions,
    general_cycles,
    general_exceptions,
    general_language_levels,
    general_languages,
    general_reasons,
    general_review_sources,
    general_risk_statuses,
    general_roles,
    general_seniorities,
    general_warrior_types,
    technologies,
)
from app.features.employee.models import (
    bill_exceptions,
    pcu_responses,
    report_employee_quality,
    report_employee_warrior,
)
from tests.features.catalogs.factories import make_row
from tests.features.companies.factories import make_account
from tests.features.employee.factories import (
    make_action,
    make_assigned_employee,
    make_assignation,
    make_comment,
    make_language,
    make_operational_profile,
    make_person,
    make_position,
    make_role,
    make_technology,
)

BASE = "/v1/employee"


def _get(client, person_id, table, **params):
    return client.get(f"{BASE}/persons/{person_id}/{table}", params=params).json()["data"]


# --- roles ----------------------------------------------------------------------------------


def test_roles_with_names_and_profile_flags_main_first(client, db):
    backend = make_row(db, general_roles, name="Backend")
    senior = make_row(db, general_seniorities, name="Senior", order=3)
    person = make_person(db)
    secondary = make_role(db, person, is_main=False)
    main = make_role(db, person, role_id=backend["id"], seniority_id=senior["id"], is_main=True)
    profile = make_operational_profile(db, main, is_certified=True, is_available=False)

    rows = _get(client, person.id, "roles")

    assert [row["id"] for row in rows] == [main.id, secondary.id]
    assert rows[0] == {
        "id": main.id, "role_id": backend["id"], "role": "Backend", "seniority_id": senior["id"], "seniority": "Senior",
        "is_main": True, "operational_profile_id": profile.id, "is_certified": True, "is_available": False,
    }
    # A role without operational profile is still listed (Retool's INNER JOIN dropped it).
    assert rows[1]["operational_profile_id"] is None


# --- languages ------------------------------------------------------------------------------


def test_languages_with_names(client, db):
    english = make_row(db, general_languages, name="English")
    advanced = make_row(db, general_language_levels, name="Advanced")
    person = make_person(db)
    language = make_language(db, person, language_id=english["id"], language_level_id=advanced["id"])

    (row,) = _get(client, person.id, "languages")

    assert (row["id"], row["language"], row["level"]) == (language.id, "English", "Advanced")
    assert row["last_evaluation_date"] == "2026-01-01T00:00:00"


# --- warrior evaluations ----------------------------------------------------------------------


def test_warrior_evaluations_newest_first(client, db):
    hero = make_row(db, general_warrior_types, name="Hero")
    person = make_person(db)
    position = make_position(db, make_role(db, person))
    common = dict(employee_position_id=position.id, avg_realization=1.0, avg_potential=1.0, warrior_type=1)
    old = make_row(db, report_employee_warrior, **common, warrior_type_id=hero["id"], created_at=datetime(2025, 1, 1))
    new = make_row(db, report_employee_warrior, **common, warrior_type_id=None, created_at=datetime(2025, 6, 1))

    rows = _get(client, person.id, "warrior-evaluations")

    assert [(row["id"], row["ew_status"]) for row in rows] == [(new["id"], None), (old["id"], "Hero")]


# --- active accounts ------------------------------------------------------------------------


def test_active_accounts_skip_ended_assignations(client, db):
    person, role, _ = make_assigned_employee(db, account_id=10, end_date=None)
    profile = make_operational_profile(db, role)
    make_assignation(db, profile, account_id=10, end_date=None)  # same account twice -> once
    make_assignation(db, profile, account_id=20, end_date=date.today())  # ends today -> active
    make_assignation(db, profile, account_id=30, end_date=date.today() - timedelta(days=1))  # ended

    assert _get(client, person.id, "active-accounts") == [10, 20]


# --- active persons of an account -----------------------------------------------------------


def test_account_active_persons_once_each_by_name(client, db):
    zoe, _, _ = make_assigned_employee(db, account_id=10, end_date=None)
    zoe.first_name = "Zoe"
    ana, ana_role, _ = make_assigned_employee(db, account_id=10, end_date=date.today())  # ends today -> active
    make_assignation(db, make_operational_profile(db, ana_role), account_id=10, end_date=None)  # twice -> once
    make_assigned_employee(db, account_id=10, end_date=date.today() - timedelta(days=1))  # ended
    make_assigned_employee(db, account_id=20, end_date=None)  # other account

    rows = client.get(f"{BASE}/accounts/10/active-persons").json()["data"]

    assert rows == [
        {"id": ana.id, "name": "Ana Gomez", "corporate_email": None, "photo_url": None},
        {"id": zoe.id, "name": "Zoe Gomez", "corporate_email": None, "photo_url": None},
    ]


# --- account risks --------------------------------------------------------------------------


def test_account_risks_latest_status_per_account(client, db):
    green = make_row(db, general_risk_statuses, name="Low", color="green")
    red = make_row(db, general_risk_statuses, name="High", color="red")
    beta, acme = make_account(db, name="Beta"), make_account(db, name="Acme")
    person, role, acme_assignation = make_assigned_employee(db, account_id=acme.id)
    beta_assignation = make_assignation(db, make_operational_profile(db, role), account_id=beta.id)

    def pcu(assignation, status, created_at):
        make_row(db, pcu_responses, assignation_id=assignation.id, risk_status_id=status["id"],
                 is_visible_to_customers=False, created_at=created_at, updated_at=created_at)

    pcu(acme_assignation, green, datetime(2025, 1, 1))
    pcu(acme_assignation, red, datetime(2025, 6, 1))
    pcu(beta_assignation, green, datetime(2025, 3, 1))

    assert _get(client, person.id, "account-risks") == [
        {"account_id": acme.id, "account": "Acme", "status": "High", "color": "red"},
        {"account_id": beta.id, "account": "Beta", "status": "Low", "color": "green"},
    ]


# --- PCU responses --------------------------------------------------------------------------


def test_pcu_responses_newest_report_first_with_names(client, db):
    red = make_row(db, general_risk_statuses, name="High", color="red")
    acme = make_account(db, name="Acme")
    person, _, assignation = make_assigned_employee(db, account_id=acme.id)

    def pcu(report_date, risk_status_id=None):
        return make_row(db, pcu_responses, assignation_id=assignation.id, report_date=report_date,
                        risk_status_id=risk_status_id, is_visible_to_customers=False,
                        created_at=datetime(2025, 1, 1), updated_at=datetime(2025, 1, 1))["id"]

    old = pcu(date(2025, 1, 15))
    new = pcu(date(2025, 6, 15), risk_status_id=red["id"])
    make_assigned_employee(db)  # another person's assignation, without PCUs

    rows = _get(client, person.id, "pcu-responses")

    assert [row["id"] for row in rows] == [new, old]
    assert (rows[0]["year_month"], rows[0]["account_id"], rows[0]["account"]) == ("2025-06", acme.id, "Acme")
    assert (rows[0]["risk_status"], rows[0]["risk_status_color"]) == ("High", "red")
    assert rows[1]["risk_status"] is None
    assert _get(client, make_person(db).id, "pcu-responses") == []


# --- quality reports ------------------------------------------------------------------------


def test_quality_reports_newest_first_with_names(client, db):
    client_review = make_row(db, general_review_sources, name="Client", type="quality")
    acme = make_account(db, name="Acme")
    person, _, assignation = make_assigned_employee(db, account_id=acme.id)

    def report(report_date, review_source_id=None):
        return make_row(db, report_employee_quality, assignation_id=assignation.id, date=report_date,
                        review_source_id=review_source_id, english_score=4.5, is_reviewed=False,
                        created_at=datetime(2025, 1, 1), updated_at=datetime(2025, 1, 1))["id"]

    old = report(date(2025, 1, 15))
    new = report(date(2025, 6, 15), review_source_id=client_review["id"])
    make_assigned_employee(db)  # another person's assignation, without reports

    rows = _get(client, person.id, "quality-reports")

    assert [row["id"] for row in rows] == [new, old]
    assert (rows[0]["date"], rows[0]["year_month"], rows[0]["english_score"]) == ("2025-06-15", "2025-06", 4.5)
    assert (rows[0]["account_id"], rows[0]["account"], rows[0]["review_source"]) == (acme.id, "Acme", "Client")
    assert rows[1]["review_source"] is None
    assert _get(client, make_person(db).id, "quality-reports") == []


# --- seniority charts -----------------------------------------------------------------------


def _tech_with_role(db, person, tech_name, role, seniority):
    tech = make_row(db, technologies, name=tech_name, role_id=role["id"])
    make_technology(db, person, technology_id=tech["id"], seniority_id=seniority["id"])


def test_role_seniority_is_the_highest_seniority_per_role(client, db):
    # Alphabetically "Junior" > "Advanced": Retool's MAX(name) paired it with Advanced's score.
    junior = make_row(db, general_seniorities, name="Junior", order=1)
    advanced = make_row(db, general_seniorities, name="Advanced", order=4)
    backend = make_row(db, general_roles, name="Backend")
    person = make_person(db)
    _tech_with_role(db, person, "Python", backend, junior)
    _tech_with_role(db, person, "Go", backend, advanced)

    assert _get(client, person.id, "role-seniorities") == [
        {"role_id": backend["id"], "role_name": "Backend", "seniority": "Advanced", "score": 4},
    ]


def test_technology_seniorities_filtered_by_exact_role(client, db):
    senior = make_row(db, general_seniorities, name="Senior", order=3)
    backend = make_row(db, general_roles, name="Backend")
    backend_lead = make_row(db, general_roles, name="Backend Lead")
    person = make_person(db)
    _tech_with_role(db, person, "Python", backend, senior)
    _tech_with_role(db, person, "Kotlin", backend_lead, senior)

    assert len(_get(client, person.id, "technology-seniorities")) == 2
    (row,) = _get(client, person.id, "technology-seniorities", role_name="backend")
    assert (row["tech"], row["role_name"], row["seniority"], row["score"]) == ("Python", "Backend", "Senior", 3)


# --- bill exceptions ------------------------------------------------------------------------


def test_bill_exceptions_with_names(client, db):
    exception = make_row(db, general_exceptions, name="Vacation")
    cycle = make_row(db, general_cycles, name="2025-01", start_date=date(2025, 1, 1))
    reason = make_row(db, general_reasons, name="Holiday")
    account = make_account(db, name="Acme")
    person, _, assignation = make_assigned_employee(db, account_id=account.id)
    row_id = make_row(
        db, bill_exceptions, assignation_id=assignation.id, account_id=account.id, exception_id=exception["id"],
        cycle_id=cycle["id"], reason_id=reason["id"], value=Decimal("120.50"), is_billable=True, for_billing=True,
        additional_info={},
    )["id"]

    (row,) = _get(client, person.id, "bill-exceptions")

    assert row["id"] == row_id
    assert (row["name"], row["exception"], row["cycle"], row["account"], row["reason"]) == (
        "Ana Gomez", "Vacation", "2025-01-01", "Acme", "Holiday",
    )
    assert row["value"] == 120.5
    assert _get(client, make_person(db).id, "bill-exceptions") == []


# --- actions and comments -------------------------------------------------------------------


def test_actions_with_names_newest_first(client, db):
    action = make_row(db, general_actions, name="1:1")
    status = make_row(db, general_action_statuses, name="Open")
    person = make_person(db)
    old = make_action(db, person, start_date=date(2025, 1, 1))
    new = make_action(db, person, start_date=date(2025, 6, 1), action_id=action["id"], action_status_id=status["id"])

    rows = _get(client, person.id, "actions")

    assert [row["id"] for row in rows] == [new.id, old.id]
    assert (rows[0]["action_name"], rows[0]["action_status_name"]) == ("1:1", "Open")


def test_comments_newest_first(client, db):
    person = make_person(db)
    old = make_comment(db, person, created_at=datetime(2025, 1, 1))
    new = make_comment(db, person, created_at=datetime(2025, 6, 1))
    make_comment(db, make_person(db))

    rows = _get(client, person.id, "comments")

    assert [row["id"] for row in rows] == [new.id, old.id]
    assert set(rows[0]) == {"id", "comment", "retool_user", "created_at"}
