"""Write use cases for the employee module. Use cases are plain functions: a class whose only
members are `__init__` and `execute` is a function with extra steps. They turn the validated
Pydantic items into dicts and delegate to BaseRepository's generic writes - the best-effort
SAVEPOINT-per-item bulk logic lives there (see app/shared/repository.py), not here.
"""

from datetime import datetime
from typing import List, Type

from pydantic import BaseModel

from app.features.employee.models import (
    EmployeeEquipment,
    EmployeeLanguage,
    EmployeePerson,
    EmployeePosition,
    EmployeeTechnology,
)
from app.features.employee.schemas.request import (
    EmployeePersonUpdateItem,
    EmployeePositionUpdateItem,
    EmployeeTechnologyBulkUpsertItem,
)
from app.features.employee.repository import EmployeeRepository
from app.infrastructure.database import Base
from app.shared.repository import BulkResult


def create(repo: EmployeeRepository, model: Type[Base], item: BaseModel) -> Base:
    """Create endpoints with no rule beyond "insert what was validated": roles, operational
    profiles, positions, technologies, languages, equipments."""
    return repo.create(model, item.model_dump(exclude_none=True), datetime.now())


def bulk_update_by_id(repo: EmployeeRepository, model: Type[Base], items: List[BaseModel]) -> List[BulkResult]:
    return repo.update_many(model, [item.model_dump(exclude_none=True) for item in items], datetime.now())


def update_person(repo: EmployeeRepository, person_id: int, item: EmployeePersonUpdateItem) -> EmployeePerson:
    return repo.update_by_id(EmployeePerson, person_id, item.model_dump(exclude_none=True), datetime.now())


def update_position(repo: EmployeeRepository, position_id: int, item: EmployeePositionUpdateItem) -> EmployeePosition:
    return repo.update_by_id(EmployeePosition, position_id, item.model_dump(exclude_none=True), datetime.now())


def bulk_delete_technologies(repo: EmployeeRepository, ids: List[int]) -> int:
    """`delete from employee_technologies where id = ANY(...)` - a single statement, not a
    best-effort batch, same semantics as the original Retool query."""
    return repo.delete_many(EmployeeTechnology, ids)


def bulk_upsert_technologies(repo: EmployeeRepository, items: List[EmployeeTechnologyBulkUpsertItem]) -> List[BulkResult]:
    return repo.upsert_many(
        EmployeeTechnology,
        [item.model_dump(exclude_none=True) for item in items],
        datetime.now(),
        required_on_create=("person_id",),
    )


def delete_language(repo: EmployeeRepository, language_row_id: int) -> bool:
    return repo.delete(EmployeeLanguage, language_row_id)


def delete_equipment(repo: EmployeeRepository, equipment_id: int) -> bool:
    return repo.delete(EmployeeEquipment, equipment_id)
