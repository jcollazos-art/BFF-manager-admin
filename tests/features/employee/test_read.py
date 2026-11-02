from tests.features.employee.factories import make_full_employee, make_person

BASE = "/v1/employee"


# --- GET /persons -------------------------------------------------------------------------


def test_list_persons_is_paginated(client, db):
    for i in range(3):
        make_person(db, first_name=f"Person{i}")

    body = client.get(f"{BASE}/persons", params={"per_page": 2, "page": 1}).json()

    assert body["total"] == 3
    assert body["page"] == 1 and body["per_page"] == 2
    assert len(body["data"]) == 2


def test_list_persons_filters_by_full_name(client, db):
    make_person(db, first_name="Ana", last_name="Gomez")
    make_person(db, first_name="Luis", last_name="Perez")

    body = client.get(f"{BASE}/persons", params={"name_search": "ana gom"}).json()

    assert [p["first_name"] for p in body["data"]] == ["Ana"]


def test_list_persons_filters_by_identification(client, db):
    make_person(db, identification="111")
    make_person(db, identification="222")

    body = client.get(f"{BASE}/persons", params={"identification": "222"}).json()

    assert [p["identification"] for p in body["data"]] == ["222"]


def test_list_persons_sorts_by_whitelisted_field(client, db):
    make_person(db, first_name="Beto")
    make_person(db, first_name="Ana")

    body = client.get(f"{BASE}/persons", params={"sort_field": "first_name", "sort_direction": "desc"}).json()

    assert [p["first_name"] for p in body["data"]] == ["Beto", "Ana"]


def test_list_persons_rejects_per_page_above_limit(client):
    response = client.get(f"{BASE}/persons", params={"per_page": 10_000})

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


# --- GET /details/{id} --------------------------------------------------------------------


def test_detail_returns_the_whole_aggregate_nested(client, db):
    person = make_full_employee(db)

    data = client.get(f"{BASE}/details/{person.id}").json()["data"]

    assert data["country_id"] == 57
    role = data["roles"][0]
    assert role["has_active_employee_position"] is True
    assert len(role["positions"]) == 1
    assignation = role["operational_profiles"][0]["assignations"][0]
    assert assignation["role_id"] == 78 and assignation["seniority_id"] == 4
    assert len(data["technologies"]) == len(data["languages"]) == len(data["equipments"]) == 1


def test_detail_serializes_numeric_columns_as_json_numbers(client, db):
    # Regression: numeric(10,2) columns were mapped as Integer and 6114.78 broke the endpoint.
    person = make_full_employee(db)

    data = client.get(f"{BASE}/details/{person.id}").json()["data"]

    assignation = data["roles"][0]["operational_profiles"][0]["assignations"][0]
    assert assignation["monthly_sales_price"] == 6114.78
    assert data["roles"][0]["positions"][0]["salary"] == 5000.0


def test_detail_of_unknown_person_is_404(client):
    response = client.get(f"{BASE}/details/999999")

    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"
