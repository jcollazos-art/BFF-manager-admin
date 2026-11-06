"""One repository per aggregate (EmployeePerson), not one per table: every child entity
(roles, operational profiles, positions, assignations, technologies, languages, equipments)
belongs to this aggregate and goes through the generic CRUD inherited from BaseRepository.
Only queries with real shape (listing, the eager-loaded detail, the positions table) are written
here; read-only views that need custom SQL live in custom_repository.py."""

from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import RowMapping, func, select
from sqlalchemy.orm import selectinload

from app.features.catalogs.tables import (
    general_contract_types,
    general_cost_centers,
    general_roles,
    general_seniorities,
    general_silos,
)
from app.features.employee.models import (
    EmployeeOperationalProfile,
    EmployeePerson,
    EmployeePosition,
    EmployeeRole,
    OperationAssignation,
)
from app.shared.repository import BaseRepository

_SORTABLE_FIELDS = {
    "id": EmployeePerson.id,
    "first_name": EmployeePerson.first_name,
    "last_name": EmployeePerson.last_name,
    "identification": EmployeePerson.identification,
    "created_at": EmployeePerson.created_at,
}


def _apply_filters(stmt, filters: Dict[str, Any]):
    if filters.get("ids"):
        stmt = stmt.where(EmployeePerson.id.in_(filters["ids"]))
    if filters.get("identification"):
        stmt = stmt.where(EmployeePerson.identification == str(filters["identification"]))
    if filters.get("name_search"):
        search = f"%{filters['name_search']}%"
        stmt = stmt.where(
            func.concat(EmployeePerson.first_name, " ", EmployeePerson.last_name).ilike(search)
        )
    return stmt


class EmployeeRepository(BaseRepository):
    def find_people(self, filters, sort_field, sort_direction, page, per_page) -> Tuple[List[EmployeePerson], int]:
        base_stmt = _apply_filters(select(EmployeePerson), filters or {})

        total = self._session.execute(
            select(func.count()).select_from(base_stmt.with_only_columns(EmployeePerson.id).subquery())
        ).scalar_one()

        sort_column = _SORTABLE_FIELDS.get(sort_field, EmployeePerson.id)
        direction = sort_column.desc() if (sort_direction or "").lower() == "desc" else sort_column.asc()

        stmt = base_stmt.order_by(direction).limit(per_page).offset((page - 1) * per_page)
        people = self._session.execute(stmt).scalars().all()
        return list(people), total

    def get_person_detail(self, person_id: int) -> Optional[EmployeePerson]:
        """Returns the person with `roles` (+ each role's `operational_profiles` +
        `assignations` + `positions`), `technologies`, `languages` and `equipments` already
        eager-loaded in one query - the single call that replaces the 7 separate Retool
        reads this module started from."""
        stmt = (
            select(EmployeePerson)
            .options(
                selectinload(EmployeePerson.city),
                selectinload(EmployeePerson.roles).selectinload(EmployeeRole.operational_profiles).selectinload(
                    EmployeeOperationalProfile.assignations
                ).selectinload(OperationAssignation.operational_profile).selectinload(
                    EmployeeOperationalProfile.role
                ),
                selectinload(EmployeePerson.roles).selectinload(EmployeeRole.positions).selectinload(
                    EmployeePosition.role
                ),
                selectinload(EmployeePerson.technologies),
                selectinload(EmployeePerson.languages),
                selectinload(EmployeePerson.equipments),
            )
            .where(EmployeePerson.id == person_id)
        )
        return self._session.execute(stmt).unique().scalar_one_or_none()

    def get_person_positions(self, person_id: int) -> List[RowMapping]:
        """Positions table of the employee's main view: one query with every catalog id
        resolved to its name, active positions first. An unknown person returns []."""
        stmt = (
            select(
                EmployeePosition.id,
                EmployeePosition.contract_type_id,
                EmployeePosition.currency,
                EmployeePosition.start_date,
                EmployeePosition.effective_date,
                EmployeePosition.end_date,
                EmployeePosition.salary,
                EmployeePosition.additional_salary,
                EmployeePosition.is_active,
                EmployeePosition.cost,
                EmployeePosition.bonus,
                EmployeePosition.silo_id,
                EmployeePosition.cost_center_id,
                general_roles.c.name.label("employee_role"),
                general_contract_types.c.name.label("contract_type"),
                general_cost_centers.c.name.label("cost_center"),
                general_seniorities.c.name.label("seniority"),
                general_silos.c.name.label("silo"),
            )
            .join(EmployeeRole, EmployeeRole.id == EmployeePosition.employee_role_id)
            .outerjoin(general_roles, general_roles.c.id == EmployeeRole.role_id)
            .outerjoin(general_contract_types, general_contract_types.c.id == EmployeePosition.contract_type_id)
            .outerjoin(general_cost_centers, general_cost_centers.c.id == EmployeePosition.cost_center_id)
            .outerjoin(general_seniorities, general_seniorities.c.id == EmployeeRole.seniority_id)
            .outerjoin(general_silos, general_silos.c.id == EmployeePosition.silo_id)
            .where(EmployeeRole.person_id == person_id)
            .order_by(EmployeePosition.is_active.desc().nulls_last(), EmployeePosition.id.desc())
        )
        return list(self._session.execute(stmt).mappings())
