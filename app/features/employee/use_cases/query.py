from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import RowMapping

from app.features.employee.models import EmployeeComment, EmployeePerson
from app.features.employee.repository import EmployeeRepository


def get_people(
    repo: EmployeeRepository,
    filters: Optional[Dict[str, Any]],
    sort_field: Optional[str],
    sort_direction: Optional[str],
    page: int,
    per_page: int,
) -> Tuple[List[EmployeePerson], int]:
    return repo.find_people(filters, sort_field, sort_direction, page, per_page)


def get_person_detail(repo: EmployeeRepository, person_id: int) -> Optional[EmployeePerson]:
    return repo.get_person_detail(person_id)


def get_person_positions(repo: EmployeeRepository, person_id: int) -> List[RowMapping]:
    return repo.get_person_positions(person_id)


def get_person_technologies(repo: EmployeeRepository, person_id: int) -> List[RowMapping]:
    return repo.get_person_technologies(person_id)


def get_person_roles(repo: EmployeeRepository, person_id: int) -> List[RowMapping]:
    return repo.get_person_roles(person_id)


def get_person_languages(repo: EmployeeRepository, person_id: int) -> List[RowMapping]:
    return repo.get_person_languages(person_id)


def get_person_warrior_evaluations(repo: EmployeeRepository, person_id: int) -> List[RowMapping]:
    return repo.get_person_warrior_evaluations(person_id)


def get_person_active_account_ids(repo: EmployeeRepository, person_id: int) -> List[int]:
    return repo.get_person_active_account_ids(person_id)


def get_person_account_risks(repo: EmployeeRepository, person_id: int) -> List[RowMapping]:
    return repo.get_person_account_risks(person_id)


def get_person_role_seniorities(repo: EmployeeRepository, person_id: int) -> List[RowMapping]:
    return repo.get_person_role_seniorities(person_id)


def get_person_technology_seniorities(
    repo: EmployeeRepository, person_id: int, role_name: Optional[str]
) -> List[RowMapping]:
    return repo.get_person_technology_seniorities(person_id, role_name)


def get_person_bill_exceptions(repo: EmployeeRepository, person_id: int) -> List[RowMapping]:
    return repo.get_person_bill_exceptions(person_id)


def get_person_actions(repo: EmployeeRepository, person_id: int) -> List[RowMapping]:
    return repo.get_person_actions(person_id)


def get_person_comments(repo: EmployeeRepository, person_id: int) -> List[EmployeeComment]:
    return repo.get_person_comments(person_id)
