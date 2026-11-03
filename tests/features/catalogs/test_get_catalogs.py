"""POST /catalogs: several catalogs in one call, each with its own filters, pagination,
sort and relations. Every catalog goes through the same generic code, so the behaviour is
checked on a few representative ones."""

from app.features.catalogs.tables import (
    general_cities,
    general_countries,
    general_languages,
    general_metrics,
    general_seniorities,
    general_silos,
)
from tests.features.catalogs.factories import make_row

URL = "/v1/catalogs"


def _post(client, *requests):
    return client.post(URL, json={"requests": list(requests)}).json()


def test_loads_several_catalogs_in_one_call(client, db):
    make_row(db, general_languages, name="English")
    make_row(db, general_seniorities, name="Senior", order=3)

    body = _post(client, {"catalog": "languages"}, {"catalog": "seniorities"})

    assert body["ok"] is True
    assert [row["name"] for row in body["results"]["languages"]["data"]] == ["English"]
    assert body["results"]["seniorities"]["data"][0]["order"] == 3


def test_paginates_with_20_per_page_by_default(client, db):
    for number in range(25):
        make_row(db, general_languages, name=f"Language {number:02}")

    first = _post(client, {"catalog": "languages"})["results"]["languages"]
    last = _post(client, {"catalog": "languages", "page": 2, "per_page": 20})["results"]["languages"]

    assert (first["total"], first["page"], first["per_page"], len(first["data"])) == (25, 1, 20, 20)
    assert [row["name"] for row in last["data"]] == [f"Language {number:02}" for number in range(20, 25)]


def test_filters(client, db):
    colombia = make_row(db, general_countries, name="Colombia")
    mexico = make_row(db, general_countries, name="Mexico")
    make_row(db, general_cities, name="Bogota", country_id=colombia["id"])
    make_row(db, general_cities, name="Medellin", country_id=colombia["id"])
    make_row(db, general_cities, name="Monterrey", country_id=mexico["id"])
    make_row(db, general_cities, name=None, country_id=mexico["id"])

    def names(filters):
        data = _post(client, {"catalog": "cities", "filters": filters})["results"]["cities"]["data"]
        return sorted(row["name"] or "<null>" for row in data)

    assert names({"country_id": colombia["id"]}) == ["Bogota", "Medellin"]            # equals
    assert names({"name": "MED"}) == ["Medellin"]                                       # text contains
    assert names({"country_id": [colombia["id"], mexico["id"]], "name": "o"}) == ["Bogota", "Monterrey"]
    assert names({"name": None}) == ["<null>"]                                          # IS NULL


def test_sorts_by_order_then_name_by_default_and_by_any_column_on_request(client, db):
    make_row(db, general_seniorities, name="Senior", order=3)
    make_row(db, general_seniorities, name="Junior", order=1)
    make_row(db, general_languages, name="Spanish")
    make_row(db, general_languages, name="English")

    body = _post(
        client,
        {"catalog": "seniorities"},
        {"catalog": "languages"},
        {"catalog": "languages", "alias": "languages_desc", "sort": "name", "direction": "desc"},
    )["results"]

    assert [row["name"] for row in body["seniorities"]["data"]] == ["Junior", "Senior"]
    assert [row["name"] for row in body["languages"]["data"]] == ["English", "Spanish"]
    assert [row["name"] for row in body["languages_desc"]["data"]] == ["Spanish", "English"]


def test_expands_relations_including_nested_ones(client, db):
    colombia = make_row(db, general_countries, name="Colombia")
    make_row(db, general_cities, name="Bogota", country_id=colombia["id"])
    make_row(db, general_cities, name="Lima", country_id=None)
    root = make_row(db, general_silos, name="Root")
    parent = make_row(db, general_silos, name="Parent", report_to_silo_id=root["id"])
    make_row(db, general_silos, name="Child", report_to_silo_id=parent["id"])

    body = _post(
        client,
        {"catalog": "cities", "relations": "country"},
        {"catalog": "silos", "relations": "report_to_silo.report_to_silo", "filters": {"name": "Child"}},
    )["results"]

    bogota, lima = body["cities"]["data"]
    assert bogota["country"]["name"] == "Colombia" and lima["country"] is None
    child = body["silos"]["data"][0]
    assert child["report_to_silo"]["name"] == "Parent"
    assert child["report_to_silo"]["report_to_silo"]["name"] == "Root"


def test_soft_deleted_metrics_are_hidden(client, db):
    make_row(db, general_metrics, name="Active")
    make_row(db, general_metrics, name="Deleted", deleted_at="2026-01-01T00:00:00")

    data = _post(client, {"catalog": "metrics"})["results"]["metrics"]["data"]

    assert [row["name"] for row in data] == ["Active"]


def test_a_bad_request_fails_alone(client, db):
    make_row(db, general_languages, name="English")

    body = _post(
        client,
        {"catalog": "nope"},
        {"catalog": "cities", "alias": "bad_filter", "filters": {"colour": "red"}},
        {"catalog": "cities", "alias": "bad_sort", "sort": "colour"},
        {"catalog": "cities", "alias": "bad_relation", "relations": "planet"},
        {"catalog": "cities", "alias": "db_error", "filters": {"country_id": "not a number"}},
        {"catalog": "languages"},
    )

    results = body["results"]
    assert body["ok"] is False
    assert results["nope"]["error"] == "unknown catalog 'nope'"
    assert "no column 'colour' to filter by" in results["bad_filter"]["error"]
    assert "no column 'colour' to sort by" in results["bad_sort"]["error"]
    assert "no relation 'planet' (available: country)" in results["bad_relation"]["error"]
    assert results["db_error"]["ok"] is False
    # A database error earlier in the batch must not poison the rest of the transaction.
    assert results["languages"]["ok"] is True and results["languages"]["data"][0]["name"] == "English"


def test_invalid_body_is_rejected(client):
    def status(body):
        return client.post(URL, json=body).status_code

    assert status({"requests": []}) == 422
    assert status({"requests": [{"catalog": "languages", "per_page": 501}]}) == 422
    assert status({"requests": [{"catalog": "languages", "direction": "up"}]}) == 422
    assert status({"requests": [{"catalog": "languages"}, {"catalog": "languages"}]}) == 422  # use alias
