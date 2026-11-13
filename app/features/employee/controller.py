"""No `Depends(get_current_user)` on this router yet - no auth feature exists in this
project (see shared/permissions.py). Once one does, it goes on `APIRouter(...,
dependencies=[...])` here, exactly like every router in bff-lsg-placement - nothing else
in this file needs to change for that."""

from typing import List, Optional

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
from app.features.employee.schemas.response import (
    EmployeeAccountPersonOut,
    EmployeeAccountRiskOut,
    EmployeeActionOut,
    EmployeeAssignationRowOut,
    EmployeeBillExceptionOut,
    EmployeeCommentOut,
    EmployeeLanguageRowOut,
    EmployeeLastPositionOut,
    EmployeeManagerOptionOut,
    EmployeeMonthlyHeadcountOut,
    EmployeeSalaryIncreaseOut,
    EmployeeTechnologyExternalIdOut,
    EmployeePersonDetailOut,
    EmployeePersonOut,
    EmployeePcuResponseOut,
    EmployeePersonSummaryOut,
    EmployeePositionRowOut,
    EmployeeQualityReportOut,
    EmployeeReportedCommentOut,
    EmployeeRoleRowOut,
    EmployeeRoleSeniorityOut,
    EmployeeTechnologyExperienceOut,
    EmployeeTechnologyRowOut,
    EmployeeTechnologySeniorityOut,
    EmployeeWarriorEvaluationOut,
)
from app.features.employee.repository import EmployeeRepository
from app.features.employee import custom_repository
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


# --- whole-company lists (no person id) - declared before any /persons/{person_id} route ---


@router.get("/persons/last-position", response_model=Envelope[List[EmployeeLastPositionOut]])
def get_employee_persons_last_position(db: Session = Depends(get_db)):
    """Every employee with personal data and their latest position, by name (custom SQL)."""
    return Envelope(data=custom_repository.get_persons_last_position(db))


@router.get("/persons/last-salary-increases", response_model=Envelope[List[EmployeeSalaryIncreaseOut]])
def get_employee_persons_last_salary_increases(db: Session = Depends(get_db)):
    """Date of each employee's latest salary increase (custom SQL)."""
    return Envelope(data=custom_repository.get_last_salary_increases(db))


@router.get("/managers/options", response_model=Envelope[List[EmployeeManagerOptionOut]])
def get_employee_manager_options(db: Session = Depends(get_db)):
    """Managers for the dashboard's managers filter, with their profile ids (custom SQL)."""
    return Envelope(data=custom_repository.get_manager_options(db))


@router.get("/headcount/monthly", response_model=Envelope[List[EmployeeMonthlyHeadcountOut]])
def get_employee_monthly_headcount(db: Session = Depends(get_db)):
    """Employees with a position in each month since 2020-01 (custom SQL)."""
    return Envelope(data=custom_repository.get_monthly_headcount(db))


@router.get("/technologies/external-ids", response_model=Envelope[List[EmployeeTechnologyExternalIdOut]])
def get_employee_technology_external_ids(repo: EmployeeRepository = Depends(get_repository)):
    """Employee technologies linked to the external knowledge catalog."""
    return Envelope(data=query.get_technology_external_ids(repo))


@router.get("/details/{person_id}", response_model=Envelope[EmployeePersonDetailOut])
#@router.get("/persons/{person_id}", response_model=Envelope[EmployeePersonDetailOut], include_in_schema=False)
def get_employee_person_detail(person_id: int, repo: EmployeeRepository = Depends(get_repository)):
    person = get_or_404(query.get_person_detail(repo, person_id), detail="employee_persons not found")
    return Envelope(data=person)


@router.get("/persons/{person_id}/summary", response_model=Envelope[EmployeePersonSummaryOut])
def get_employee_person_summary(person_id: int, db: Session = Depends(get_db)):
    """Header of the employee's main view with names instead of ids (custom SQL)."""
    summary = get_or_404(custom_repository.get_person_summary(db, person_id), detail="employee_persons not found")
    return Envelope(data=summary)


@router.get("/persons/{person_id}/positions", response_model=Envelope[List[EmployeePositionRowOut]])
def get_employee_person_positions(person_id: int, repo: EmployeeRepository = Depends(get_repository)):
    """Positions table of the employee's main view, active first, with names.
    An unknown person returns an empty list."""
    return Envelope(data=query.get_person_positions(repo, person_id))


@router.get("/persons/{person_id}/technologies", response_model=Envelope[List[EmployeeTechnologyRowOut]])
def get_employee_person_technologies(person_id: int, repo: EmployeeRepository = Depends(get_repository)):
    """Technologies of the employee's main view with the seniority name, principal first.
    An unknown person returns an empty list."""
    return Envelope(data=query.get_person_technologies(repo, person_id))


# The rest of the employee's main view: one endpoint per table/chart. An unknown person
# returns an empty list in all of them.


@router.get("/persons/{person_id}/roles", response_model=Envelope[List[EmployeeRoleRowOut]])
def get_employee_person_roles(person_id: int, repo: EmployeeRepository = Depends(get_repository)):
    """Roles with names and operational-profile flags, main role first."""
    return Envelope(data=query.get_person_roles(repo, person_id))


@router.get("/persons/{person_id}/assignations", response_model=Envelope[List[EmployeeAssignationRowOut]])
def get_employee_person_assignations(person_id: int, db: Session = Depends(get_db)):
    """Each assignation paired with the positions it overlaps, with the margin (custom SQL)."""
    return Envelope(data=custom_repository.get_person_assignations(db, person_id))


@router.get("/persons/{person_id}/languages", response_model=Envelope[List[EmployeeLanguageRowOut]])
def get_employee_person_languages(person_id: int, repo: EmployeeRepository = Depends(get_repository)):
    """Every language with its level (the English card filters `language == "English"`)."""
    return Envelope(data=query.get_person_languages(repo, person_id))


@router.get(
    "/persons/{person_id}/technology-experience", response_model=Envelope[List[EmployeeTechnologyExperienceOut]]
)
def get_employee_person_technology_experience(person_id: int, db: Session = Depends(get_db)):
    """Technologies with the experience gained on each account using them (custom SQL)."""
    return Envelope(data=custom_repository.get_person_technology_experience(db, person_id))


@router.get("/persons/{person_id}/role-seniorities", response_model=Envelope[List[EmployeeRoleSeniorityOut]])
def get_employee_person_role_seniorities(person_id: int, repo: EmployeeRepository = Depends(get_repository)):
    """Highest technology seniority per role (seniority-by-role chart)."""
    return Envelope(data=query.get_person_role_seniorities(repo, person_id))


@router.get(
    "/persons/{person_id}/technology-seniorities", response_model=Envelope[List[EmployeeTechnologySeniorityOut]]
)
def get_employee_person_technology_seniorities(
    person_id: int,
    role_name: Optional[str] = Query(None, description="Only this role (case-insensitive exact name)"),
    repo: EmployeeRepository = Depends(get_repository),
):
    """Technologies with seniority and role; `role_name` filters by the role picked in the chart."""
    return Envelope(data=query.get_person_technology_seniorities(repo, person_id, role_name))


@router.get("/persons/{person_id}/warrior-evaluations", response_model=Envelope[List[EmployeeWarriorEvaluationOut]])
def get_employee_person_warrior_evaluations(person_id: int, repo: EmployeeRepository = Depends(get_repository)):
    """Early-warning (warrior) evaluations, newest first."""
    return Envelope(data=query.get_person_warrior_evaluations(repo, person_id))


@router.get("/persons/{person_id}/account-risks", response_model=Envelope[List[EmployeeAccountRiskOut]])
def get_employee_person_account_risks(person_id: int, repo: EmployeeRepository = Depends(get_repository)):
    """Latest PCU risk status per account, by account name."""
    return Envelope(data=query.get_person_account_risks(repo, person_id))


@router.get("/accounts/{account_id}/active-persons", response_model=Envelope[List[EmployeeAccountPersonOut]])
def get_employee_account_active_persons(account_id: int, repo: EmployeeRepository = Depends(get_repository)):
    """Employees with an assignation on the account that hasn't ended, by name."""
    return Envelope(data=query.get_account_active_persons(repo, account_id))


@router.get("/persons/{person_id}/pcu-responses", response_model=Envelope[List[EmployeePcuResponseOut]])
def get_employee_person_pcu_responses(person_id: int, repo: EmployeeRepository = Depends(get_repository)):
    """PCU responses with account and risk status, newest report first."""
    return Envelope(data=query.get_person_pcu_responses(repo, person_id))


@router.get("/persons/{person_id}/quality-reports", response_model=Envelope[List[EmployeeQualityReportOut]])
def get_employee_person_quality_reports(person_id: int, repo: EmployeeRepository = Depends(get_repository)):
    """Quality reports with account and review source, newest first."""
    return Envelope(data=query.get_person_quality_reports(repo, person_id))


@router.get("/persons/{person_id}/active-accounts", response_model=Envelope[List[int]])
def get_employee_person_active_accounts(person_id: int, repo: EmployeeRepository = Depends(get_repository)):
    """Ids of the accounts where the employee has an assignation that hasn't ended."""
    return Envelope(data=query.get_person_active_account_ids(repo, person_id))


@router.get("/persons/{person_id}/bill-exceptions", response_model=Envelope[List[EmployeeBillExceptionOut]])
def get_employee_person_bill_exceptions(person_id: int, repo: EmployeeRepository = Depends(get_repository)):
    """Bill exceptions of the employee's assignations, newest first."""
    return Envelope(data=query.get_person_bill_exceptions(repo, person_id))


@router.get("/persons/{person_id}/actions", response_model=Envelope[List[EmployeeActionOut]])
def get_employee_person_actions(person_id: int, repo: EmployeeRepository = Depends(get_repository)):
    """Actions with action and status names, newest first."""
    return Envelope(data=query.get_person_actions(repo, person_id))


@router.get("/persons/{person_id}/comments", response_model=Envelope[List[EmployeeCommentOut]])
def get_employee_person_comments(person_id: int, repo: EmployeeRepository = Depends(get_repository)):
    """Comments, newest first."""
    return Envelope(data=query.get_person_comments(repo, person_id))


@router.get("/persons/{person_id}/reported-comments", response_model=Envelope[List[EmployeeReportedCommentOut]])
def get_employee_person_reported_comments(person_id: int, repo: EmployeeRepository = Depends(get_repository)):
    """Comments with who reported them (employee_person_comments), newest first."""
    return Envelope(data=query.get_person_reported_comments(repo, person_id))


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
