"""Write use cases for the employee module. Use cases are plain functions: a class whose only
members are `__init__` and `execute` is a function with extra steps. They turn the validated
Pydantic items into dicts and delegate to BaseRepository's generic writes - the best-effort
SAVEPOINT-per-item bulk logic lives there (see app/shared/repository.py), not here.

Creating and updating share one path: `bulk_upsert` (item with `id` -> update, without ->
create). Deletes stay separate.
"""

from datetime import datetime
from typing import List, Sequence, Type

from pydantic import BaseModel

from app.features.employee.models import EmployeeEquipment, EmployeeLanguage, EmployeeTechnology
from app.features.employee.repository import EmployeeRepository
from app.infrastructure.database import Base
from app.shared.repository import BulkResult


def bulk_upsert(
    repo: EmployeeRepository,
    model: Type[Base],
    items: List[BaseModel],
    required_on_create: Sequence[str] = (),
) -> List[BulkResult]:
    return repo.upsert_many(
        model,
        [item.model_dump(exclude_none=True) for item in items],
        datetime.now(),
        required_on_create=required_on_create,
    )


def bulk_delete_technologies(repo: EmployeeRepository, ids: List[int]) -> int:
    """`delete from employee_technologies where id = ANY(...)` - a single statement, not a
    best-effort batch, same semantics as the original Retool query."""
    return repo.delete_many(EmployeeTechnology, ids)


def delete_language(repo: EmployeeRepository, language_row_id: int) -> bool:
    return repo.delete(EmployeeLanguage, language_row_id)


def delete_equipment(repo: EmployeeRepository, equipment_id: int) -> bool:
    return repo.delete(EmployeeEquipment, equipment_id)
