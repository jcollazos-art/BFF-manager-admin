"""No `Depends(get_current_user)` on this router yet - no auth feature exists in this
project (see shared/permissions.py). Once one does, it goes on `APIRouter(...,
dependencies=[...])` here, exactly like every router in bff-lsg-placement - nothing else
in this file needs to change for that."""

from typing import List

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.features.employee.schemas.request import (
    EmployeeEquipmentBulkUpdateItem,
    EmployeeEquipmentCreateItem,
    EmployeeLanguageBulkUpdateItem,
    EmployeeLanguageCreateItem,
    EmployeeOperationalProfileBulkUpdateItem,
    EmployeeOperationalProfileCreateItem,
    EmployeePersonUpdateItem,
    EmployeePositionBulkUpdateItem,
    EmployeePositionCreateItem,
    EmployeePositionUpdateItem,
    EmployeeRoleCreateItem,
    EmployeeTechnologyBulkUpdateItem,
    EmployeeTechnologyBulkUpsertItem,
    EmployeeTechnologyCreateItem,
    FilterEmployeePerson,
    OperationAssignationBulkUpdateItem,
)
from app.features.employee.schemas.response import (
    EmployeeEquipmentOut,
    EmployeeLanguageOut,
    EmployeeOperationalProfileOut,
    EmployeePersonDetailOut,
    EmployeePersonOut,
    EmployeePositionOut,
    EmployeeRoleOut,
    EmployeeTechnologyOut,
)
from app.features.employee.models import (
    EmployeeEquipment,
    EmployeeLanguage,
    EmployeeOperationalProfile,
    EmployeePosition,
    EmployeeRole,
    EmployeeTechnology,
    OperationAssignation,
)
from app.features.employee.repository import EmployeeRepository
from app.features.employee.use_cases import query, write
from app.infrastructure.database import get_db
from app.shared.errors import get_or_404
from app.shared.pagination import Pagination, Sort, pagination_params, sort_params
from app.shared.query_filters import merge_query_filters
from app.shared.responses import Envelope, Page

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


@router.patch("/persons/{person_id}", response_model=Envelope[EmployeePersonOut])
def update_employee_person(person_id: int, item: EmployeePersonUpdateItem, repo: EmployeeRepository = Depends(get_repository)):
    return Envelope(data=write.update_person(repo, person_id, item))


@router.post("/roles", response_model=Envelope[EmployeeRoleOut], status_code=201)
def create_employee_role(item: EmployeeRoleCreateItem, repo: EmployeeRepository = Depends(get_repository)):
    return Envelope(data=write.create(repo, EmployeeRole, item))


@router.post("/operational-profiles", response_model=Envelope[EmployeeOperationalProfileOut], status_code=201)
def create_operational_profile(item: EmployeeOperationalProfileCreateItem, repo: EmployeeRepository = Depends(get_repository)):
    return Envelope(data=write.create(repo, EmployeeOperationalProfile, item))


@router.patch("/operational-profiles/bulk")
def bulk_update_operational_profiles(items: List[EmployeeOperationalProfileBulkUpdateItem], repo: EmployeeRepository = Depends(get_repository)):
    results = write.bulk_update_by_id(repo, EmployeeOperationalProfile, items)
    return {"ok": all(r["ok"] for r in results), "results": results}


@router.post("/positions", response_model=Envelope[EmployeePositionOut], status_code=201)
def create_position(item: EmployeePositionCreateItem, repo: EmployeeRepository = Depends(get_repository)):
    return Envelope(data=write.create(repo, EmployeePosition, item))


# Must be declared before /positions/{position_id}: routes match in order, so otherwise
# "bulk" is captured as position_id and the request fails with 422.
@router.patch("/positions/bulk")
def bulk_update_positions(items: List[EmployeePositionBulkUpdateItem], repo: EmployeeRepository = Depends(get_repository)):
    results = write.bulk_update_by_id(repo, EmployeePosition, items)
    return {"ok": all(r["ok"] for r in results), "results": results}


@router.patch("/positions/{position_id}", response_model=Envelope[EmployeePositionOut])
def update_position(position_id: int, item: EmployeePositionUpdateItem, repo: EmployeeRepository = Depends(get_repository)):
    return Envelope(data=write.update_position(repo, position_id, item))


@router.patch("/assignations/bulk")
def bulk_update_assignations(items: List[OperationAssignationBulkUpdateItem], repo: EmployeeRepository = Depends(get_repository)):
    results = write.bulk_update_by_id(repo, OperationAssignation, items)
    return {"ok": all(r["ok"] for r in results), "results": results}


@router.post("/technologies", response_model=Envelope[EmployeeTechnologyOut], status_code=201)
def create_technology(item: EmployeeTechnologyCreateItem, repo: EmployeeRepository = Depends(get_repository)):
    return Envelope(data=write.create(repo, EmployeeTechnology, item))


@router.patch("/technologies/bulk")
def bulk_update_technologies(items: List[EmployeeTechnologyBulkUpdateItem], repo: EmployeeRepository = Depends(get_repository)):
    results = write.bulk_update_by_id(repo, EmployeeTechnology, items)
    return {"ok": all(r["ok"] for r in results), "results": results}


@router.post("/technologies/bulk-upsert")
def bulk_upsert_technologies(items: List[EmployeeTechnologyBulkUpsertItem], repo: EmployeeRepository = Depends(get_repository)):
    results = write.bulk_upsert_technologies(repo, items)
    return {"ok": all(r["ok"] for r in results), "results": results}


@router.delete("/technologies")
def bulk_delete_technologies(ids: List[int] = Query(...), repo: EmployeeRepository = Depends(get_repository)):
    return {"deleted": write.bulk_delete_technologies(repo, ids)}


@router.post("/languages", response_model=Envelope[EmployeeLanguageOut], status_code=201)
def create_language(item: EmployeeLanguageCreateItem, repo: EmployeeRepository = Depends(get_repository)):
    return Envelope(data=write.create(repo, EmployeeLanguage, item))


@router.patch("/languages/bulk")
def bulk_update_languages(items: List[EmployeeLanguageBulkUpdateItem], repo: EmployeeRepository = Depends(get_repository)):
    results = write.bulk_update_by_id(repo, EmployeeLanguage, items)
    return {"ok": all(r["ok"] for r in results), "results": results}


@router.delete("/languages/{language_row_id}")
def delete_language(language_row_id: int, repo: EmployeeRepository = Depends(get_repository)):
    return {"deleted": write.delete_language(repo, language_row_id)}


@router.post("/equipments", response_model=Envelope[EmployeeEquipmentOut], status_code=201)
def create_equipment(item: EmployeeEquipmentCreateItem, repo: EmployeeRepository = Depends(get_repository)):
    return Envelope(data=write.create(repo, EmployeeEquipment, item))


@router.patch("/equipments/bulk")
def bulk_update_equipments(items: List[EmployeeEquipmentBulkUpdateItem], repo: EmployeeRepository = Depends(get_repository)):
    results = write.bulk_update_by_id(repo, EmployeeEquipment, items)
    return {"ok": all(r["ok"] for r in results), "results": results}


@router.delete("/equipments/{equipment_id}")
def delete_equipment(equipment_id: int, repo: EmployeeRepository = Depends(get_repository)):
    return {"deleted": write.delete_equipment(repo, equipment_id)}
