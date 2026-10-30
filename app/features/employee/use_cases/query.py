from typing import Any, Dict, List, Optional, Tuple

from app.features.employee.models import EmployeePerson
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
