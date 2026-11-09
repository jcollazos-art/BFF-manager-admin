from datetime import date

from tests.features.companies.factories import make_account, make_team


def test_account_options_by_name(client, db):
    zeta = make_account(db, name="Zeta")
    acme = make_account(db, name="Acme", end_date=date(2025, 12, 31), billing_model="HOURLY")

    data = client.get("/v1/companies/accounts/options").json()["data"]

    assert [row for row in data if row["id"] in (zeta.id, acme.id)] == [
        {"id": acme.id, "name": "Acme", "end_date": "2025-12-31", "billing_model": "HOURLY"},
        {"id": zeta.id, "name": "Zeta", "end_date": None, "billing_model": None},
    ]


def test_team_options_by_name_with_their_account(client, db):
    account = make_account(db)
    web = make_team(db, account, name="Web")
    core = make_team(db, account, name="Core")

    data = client.get("/v1/companies/teams/options").json()["data"]

    assert [row for row in data if row["id"] in (web.id, core.id)] == [
        {"id": core.id, "name": "Core", "account_id": account.id},
        {"id": web.id, "name": "Web", "account_id": account.id},
    ]
