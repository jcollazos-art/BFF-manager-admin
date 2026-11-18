from datetime import date, datetime

from tests.features.companies.factories import make_account, make_account_poc, make_team


def test_account_options_by_name(client, db):
    zeta = make_account(db, name="Zeta")
    acme = make_account(db, name="Acme", end_date=date(2025, 12, 31), billing_model="HOURLY")

    data = client.get("/v1/companies/accounts/options").json()["data"]

    assert [row for row in data if row["id"] in (zeta.id, acme.id)] == [
        {"id": acme.id, "name": "Acme", "end_date": "2025-12-31", "billing_model": "HOURLY"},
        {"id": zeta.id, "name": "Zeta", "end_date": None, "billing_model": None},
    ]


def test_account_options_only_the_given_ids(client, db):
    zeta, acme = make_account(db, name="Zeta"), make_account(db, name="Acme")
    make_account(db, name="Other")

    data = client.get("/v1/companies/accounts/options", params={"ids": [zeta.id, acme.id]}).json()["data"]

    assert [row["id"] for row in data] == [acme.id, zeta.id]


def test_team_options_by_name_with_their_account(client, db):
    account = make_account(db)
    web = make_team(db, account, name="Web")
    core = make_team(db, account, name="Core")

    data = client.get("/v1/companies/teams/options").json()["data"]

    assert [row for row in data if row["id"] in (web.id, core.id)] == [
        {"id": core.id, "name": "Core", "account_id": account.id},
        {"id": web.id, "name": "Web", "account_id": account.id},
    ]


def test_account_pocs_active_ones_by_name(client, db):
    account, other = make_account(db), make_account(db)
    zoe = make_account_poc(db, account, person={"first_name": "Zoe", "corporate_email": "zoe@client.com"})
    ana = make_account_poc(db, account, person={"first_name": "Ana"})
    make_account_poc(db, account, is_active=False)
    make_account_poc(db, account, deleted_at=datetime(2026, 1, 2))  # soft-deleted, still flagged active
    make_account_poc(db, other)

    data = client.get(f"/v1/companies/accounts/{account.id}/pocs").json()["data"]

    assert data == [
        {"id": ana.id, "name": "Ana Diaz", "email": None},
        {"id": zoe.id, "name": "Zoe Diaz", "email": "zoe@client.com"},
    ]
