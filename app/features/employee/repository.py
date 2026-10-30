"""One repository per aggregate (EmployeePerson), not one per table: every child entity
(roles, operational profiles, positions, assignations, technologies, languages, equipments)
belongs to this aggregate and goes through the generic CRUD inherited from BaseRepository.
Only queries with real shape (listing, the eager-loaded detail) are written here."""

from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

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
