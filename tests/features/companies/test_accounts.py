from tests.features.companies.factories import make_account


def test_account_options_are_id_and_name_by_name(client, db):
    zeta = make_account(db, name="Zeta")
    acme = make_account(db, name="Acme")

    data = client.get("/v1/companies/accounts/options").json()["data"]

    assert [row for row in data if row["id"] in (zeta.id, acme.id)] == [
        {"id": acme.id, "name": "Acme"},
        {"id": zeta.id, "name": "Zeta"},
    ]
