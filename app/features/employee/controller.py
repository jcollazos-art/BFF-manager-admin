"""No `Depends(get_current_user)` on this router yet - no auth feature exists in this
project (see shared/permissions.py). Once one does, it goes on `APIRouter(...,
dependencies=[...])` here, exactly like every router in bff-lsg-placement - nothing else
in this file needs to change for that."""

from typing import List

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.features.employee.models import (
    EmployeeEquipment,
    EmployeeLanguage,
    EmployeeOperationalProfile,
    EmployeePerson,
    EmployeePosition,
    EmployeeRole,
    EmployeeTechnology,
    OperationAssignation,
)
from app.features.employee.schemas.request import (
    EmployeeEquipmentUpsertItem,
    EmployeeLanguageUpsertItem,
    EmployeeOperationalProfileUpsertItem,
    EmployeePersonUpsertItem,
    EmployeePositionUpsertItem,
    EmployeeRoleUpsertItem,
    EmployeeTechnologyUpsertItem,
    FilterEmployeePerson,
    OperationAssignationUpsertItem,
)
from app.features.employee.schemas.response import EmployeePersonDetailOut, EmployeePersonOut
from app.features.employee.repository import EmployeeRepository
from app.features.employee.use_cases import query, write
from app.infrastructure.database import get_db
from app.shared.errors import get_or_404
from app.shared.pagination import Pagination, Sort, pagination_params, sort_params
from app.shared.query_filters import merge_query_filters
from app.shared.responses import BulkResponse, Envelope, Page

router = APIRouter(prefix="/employee", tags=["Employee"])


def get_repository(db: Session = Depends(get_db)) -> EmployeeRepository:
    return EmployeeRepository(db)


@router.get("/persons", response_model=Page[EmployeePersonOut])
def get_employee_persons(
    filters: FilterEmployeePerson = Depends(),
    request: Request = None,
    pagination: Pagination = Depends(pagination_params()),
    sort: Sort = Depends(sort_params(default_field="id")),
    repo: EmployeeRepository = Depends(get_repository),
):
    filter_dict = merge_query_filters(request, filters)
    data, total = query.get_people(
        repo, filters=filter_dict, sort_field=sort.sort_field, sort_direction=sort.sort_direction,
        page=pagination.page, per_page=pagination.per_page,
    )
    return Page(data=data, total=total, page=pagination.page, per_page=pagination.per_page)


@router.get("/details/{person_id}", response_model=Envelope[EmployeePersonDetailOut])
#@router.get("/persons/{person_id}", response_model=Envelope[EmployeePersonDetailOut], include_in_schema=False)
def get_employee_person_detail(person_id: int, repo: EmployeeRepository = Depends(get_repository)):
    person = get_or_404(query.get_person_detail(repo, person_id), detail="employee_persons not found")
    return Envelope(data=person)


# --- writes -------------------------------------------------------------------------------
# One POST /<resource>/bulk-upsert per entity covers create and update, for one item or many:
# item with `id` -> update (only the fields sent change); without `id` -> create, which requires
# the fields in `required_on_create` (the parent FK). Best-effort per item, see BulkResponse.


@router.post("/persons/bulk-upsert", response_model=BulkResponse)
def bulk_upsert_persons(items: List[EmployeePersonUpsertItem], repo: EmployeeRepository = Depends(get_repository)):
    return BulkResponse.from_results(
        write.bulk_upsert(repo, EmployeePerson, items, required_on_create=("first_name", "last_name"))
    )


@router.post("/roles/bulk-upsert", response_model=BulkResponse)
def bulk_upsert_roles(items: List[EmployeeRoleUpsertItem], repo: EmployeeRepository = Depends(get_repository)):
    return BulkResponse.from_results(write.bulk_upsert(repo, EmployeeRole, items, required_on_create=("person_id",)))


@router.post("/operational-profiles/bulk-upsert", response_model=BulkResponse)
def bulk_upsert_operational_profiles(
    items: List[EmployeeOperationalProfileUpsertItem], repo: EmployeeRepository = Depends(get_repository)
):
    return BulkResponse.from_results(
        write.bulk_upsert(repo, EmployeeOperationalProfile, items, required_on_create=("employee_role_id",))
    )


@router.post("/positions/bulk-upsert", response_model=BulkResponse)
def bulk_upsert_positions(items: List[EmployeePositionUpsertItem], repo: EmployeeRepository = Depends(get_repository)):
    return BulkResponse.from_results(
        write.bulk_upsert(repo, EmployeePosition, items, required_on_create=("employee_role_id",))
    )


@router.post("/assignations/bulk-upsert", response_model=BulkResponse)
def bulk_upsert_assignations(items: List[OperationAssignationUpsertItem], repo: EmployeeRepository = Depends(get_repository)):
    return BulkResponse.from_results(
        write.bulk_upsert(repo, OperationAssignation, items, required_on_create=("operational_profile_id",))
    )


@router.post("/technologies/bulk-upsert", response_model=BulkResponse)
def bulk_upsert_technologies(items: List[EmployeeTechnologyUpsertItem], repo: EmployeeRepository = Depends(get_repository)):
    return BulkResponse.from_results(
        write.bulk_upsert(repo, EmployeeTechnology, items, required_on_create=("person_id",))
    )


@router.post("/languages/bulk-upsert", response_model=BulkResponse)
def bulk_upsert_languages(items: List[EmployeeLanguageUpsertItem], repo: EmployeeRepository = Depends(get_repository)):
    return BulkResponse.from_results(write.bulk_upsert(repo, EmployeeLanguage, items, required_on_create=("person_id",)))


@router.post("/equipments/bulk-upsert", response_model=BulkResponse)
def bulk_upsert_equipments(items: List[EmployeeEquipmentUpsertItem], repo: EmployeeRepository = Depends(get_repository)):
    return BulkResponse.from_results(write.bulk_upsert(repo, EmployeeEquipment, items, required_on_create=("person_id",)))


# --- deletes ------------------------------------------------------------------------------


@router.delete("/technologies")
def bulk_delete_technologies(ids: List[int] = Query(...), repo: EmployeeRepository = Depends(get_repository)):
    return {"deleted": write.bulk_delete_technologies(repo, ids)}


@router.delete("/languages/{language_row_id}")
def delete_language(language_row_id: int, repo: EmployeeRepository = Depends(get_repository)):
    return {"deleted": write.delete_language(repo, language_row_id)}


@router.delete("/equipments/{equipment_id}")
def delete_equipment(equipment_id: int, repo: EmployeeRepository = Depends(get_repository)):
    return {"deleted": write.delete_equipment(repo, equipment_id)}
