from app.features.employee.models import EmployeeEquipment, EmployeeLanguage, EmployeeTechnology
from tests.features.employee.factories import make_equipment, make_language, make_person, make_technology

BASE = "/v1/employee"


def test_bulk_delete_technologies_removes_only_the_given_ids(client, db):
    person = make_person(db)
    keep, drop_a, drop_b = (make_technology(db, person) for _ in range(3))

    response = client.delete(f"{BASE}/technologies", params=[("ids", drop_a.id), ("ids", drop_b.id)])

    assert response.json() == {"deleted": 2}
    db.expunge_all()  # bypass the session cache: read what is really in the database
    assert db.get(EmployeeTechnology, keep.id) is not None
    assert db.get(EmployeeTechnology, drop_a.id) is None


def test_delete_language(client, db):
    language = make_language(db, make_person(db))

    assert client.delete(f"{BASE}/languages/{language.id}").json() == {"deleted": True}
    db.expunge_all()  # bypass the session cache: read what is really in the database
    assert db.get(EmployeeLanguage, language.id) is None


def test_delete_equipment(client, db):
    equipment = make_equipment(db, make_person(db))

    assert client.delete(f"{BASE}/equipments/{equipment.id}").json() == {"deleted": True}
    db.expunge_all()  # bypass the session cache: read what is really in the database
    assert db.get(EmployeeEquipment, equipment.id) is None


def test_delete_of_unknown_row_reports_false(client):
    assert client.delete(f"{BASE}/languages/999999").json() == {"deleted": False}
