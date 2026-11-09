"""One repository per aggregate (EmployeePerson), not one per table: every child entity
(roles, operational profiles, positions, assignations, technologies, languages, equipments)
belongs to this aggregate and goes through the generic CRUD inherited from BaseRepository.
Only queries with real shape (listing, the eager-loaded detail, the tables of the employee's
main view) are written here; read-only views that need custom SQL live in custom_repository.py.

Every `get_person_*` table query returns [] for an unknown person, and resolves catalog ids to
names with LEFT JOINs, so a row with a missing/unknown catalog id is still returned (Retool's
INNER JOINs silently dropped it)."""

from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import RowMapping, func, or_, select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.orm import selectinload

from app.features.catalogs.tables import (
    general_action_statuses,
    general_actions,
    general_contract_types,
    general_cost_centers,
    general_cycles,
    general_exceptions,
    general_language_levels,
    general_languages,
    general_reasons,
    general_risk_statuses,
    general_roles,
    general_seniorities,
    general_silos,
    general_warrior_types,
    technologies,
)
from app.features.companies.models import CompanyAccount
from app.features.employee.models import (
    EmployeeAction,
    EmployeeComment,
    EmployeeLanguage,
    EmployeeOperationalProfile,
    EmployeePerson,
    EmployeePosition,
    EmployeeRole,
    EmployeeTechnology,
    OperationAssignation,
    bill_exceptions,
    pcu_responses,
    report_employee_warrior,
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

    def get_person_technologies(self, person_id: int) -> List[RowMapping]:
        """Technologies of the employee with the seniority name resolved, principal first.
        LEFT JOIN on purpose: a technology without (or with an unknown) seniority is still
        returned, with `seniority` null - Retool's INNER JOIN dropped it. An unknown person
        returns []."""
        stmt = (
            select(
                EmployeeTechnology.id,
                EmployeeTechnology.person_id,
                EmployeeTechnology.knowledge_external_id,
                EmployeeTechnology.seniority_external_id,
                EmployeeTechnology.is_principal,
                EmployeeTechnology.is_verified,
                general_seniorities.c.name.label("seniority"),
                general_seniorities.c.order.label("score"),
            )
            .outerjoin(general_seniorities, general_seniorities.c.id == EmployeeTechnology.seniority_external_id)
            .where(EmployeeTechnology.person_id == person_id)
            .order_by(EmployeeTechnology.is_principal.desc().nulls_last(), EmployeeTechnology.id)
        )
        return list(self._session.execute(stmt).mappings())

    def get_person_roles(self, person_id: int) -> List[RowMapping]:
        """Roles with their names and operational-profile flags, main role first. One row per
        operational profile; a role without one is still returned, with the flags null."""
        stmt = (
            select(
                EmployeeRole.id,
                EmployeeRole.role_id,
                general_roles.c.name.label("role"),
                EmployeeRole.seniority_id,
                general_seniorities.c.name.label("seniority"),
                EmployeeRole.is_main,
                EmployeeOperationalProfile.id.label("operational_profile_id"),
                EmployeeOperationalProfile.is_certified,
                EmployeeOperationalProfile.is_available,
            )
            .outerjoin(EmployeeOperationalProfile, EmployeeOperationalProfile.employee_role_id == EmployeeRole.id)
            .outerjoin(general_roles, general_roles.c.id == EmployeeRole.role_id)
            .outerjoin(general_seniorities, general_seniorities.c.id == EmployeeRole.seniority_id)
            .where(EmployeeRole.person_id == person_id)
            .order_by(EmployeeRole.is_main.desc().nulls_last(), EmployeeRole.id, EmployeeOperationalProfile.id)
        )
        return list(self._session.execute(stmt).mappings())

    def get_person_languages(self, person_id: int) -> List[RowMapping]:
        """Every language of the employee with its level. Retool's "english" query filtered
        `language_level_id = 3`, which is the level *Intermediate*, not English
        (`language_id = 2`); the client filters by `language` instead."""
        stmt = (
            select(
                EmployeeLanguage.id,
                EmployeeLanguage.language_id,
                general_languages.c.name.label("language"),
                EmployeeLanguage.language_level_id,
                general_language_levels.c.name.label("level"),
                EmployeeLanguage.created_at.label("last_evaluation_date"),
            )
            .outerjoin(general_languages, general_languages.c.id == EmployeeLanguage.language_id)
            .outerjoin(general_language_levels, general_language_levels.c.id == EmployeeLanguage.language_level_id)
            .where(EmployeeLanguage.person_id == person_id)
            .order_by(general_languages.c.name, EmployeeLanguage.id)
        )
        return list(self._session.execute(stmt).mappings())

    def get_person_warrior_evaluations(self, person_id: int) -> List[RowMapping]:
        """Early-warning (warrior) evaluations of every position of the employee, newest first."""
        rew = report_employee_warrior
        stmt = (
            select(
                rew.c.id,
                rew.c.employee_position_id,
                general_warrior_types.c.name.label("ew_status"),
                rew.c.created_at.label("last_evaluation_date"),
            )
            .join(EmployeePosition, EmployeePosition.id == rew.c.employee_position_id)
            .join(EmployeeRole, EmployeeRole.id == EmployeePosition.employee_role_id)
            .outerjoin(general_warrior_types, general_warrior_types.c.id == rew.c.warrior_type_id)
            .where(EmployeeRole.person_id == person_id)
            .order_by(rew.c.created_at.desc(), rew.c.id.desc())
        )
        return list(self._session.execute(stmt).mappings())

    def get_person_active_account_ids(self, person_id: int) -> List[int]:
        """Accounts where the employee has an assignation that hasn't ended (no end_date, or
        ending today or later)."""
        stmt = (
            select(OperationAssignation.account_id)
            .join(EmployeeOperationalProfile, EmployeeOperationalProfile.id == OperationAssignation.operational_profile_id)
            .join(EmployeeRole, EmployeeRole.id == EmployeeOperationalProfile.employee_role_id)
            .where(
                EmployeeRole.person_id == person_id,
                OperationAssignation.account_id.is_not(None),
                or_(OperationAssignation.end_date.is_(None), OperationAssignation.end_date >= func.current_date()),
            )
            .distinct()
            .order_by(OperationAssignation.account_id)
        )
        return list(self._session.execute(stmt).scalars())

    def get_person_account_risks(self, person_id: int) -> List[RowMapping]:
        """Latest PCU risk status of each account the employee has been assigned to, by account
        name. DISTINCT ON the account id, not only its name as Retool did, so two accounts
        sharing a name aren't merged."""
        pcu = pcu_responses
        latest = (
            select(
                CompanyAccount.id.label("account_id"),
                CompanyAccount.name.label("account"),
                general_risk_statuses.c.name.label("status"),
                general_risk_statuses.c.color,
            )
            .select_from(pcu)
            .join(OperationAssignation, OperationAssignation.id == pcu.c.assignation_id)
            .join(EmployeeOperationalProfile, EmployeeOperationalProfile.id == OperationAssignation.operational_profile_id)
            .join(EmployeeRole, EmployeeRole.id == EmployeeOperationalProfile.employee_role_id)
            .join(CompanyAccount, CompanyAccount.id == OperationAssignation.account_id)
            .outerjoin(general_risk_statuses, general_risk_statuses.c.id == pcu.c.risk_status_id)
            .where(EmployeeRole.person_id == person_id)
            .ext(distinct_on(CompanyAccount.id))
            .order_by(CompanyAccount.id, pcu.c.created_at.desc(), pcu.c.id.desc())
            .subquery()
        )
        stmt = select(latest).order_by(latest.c.account, latest.c.account_id)
        return list(self._session.execute(stmt).mappings())

    def get_person_pcu_responses(self, person_id: int) -> List[RowMapping]:
        """PCU responses of every assignation of the employee, newest report first, with the
        account and risk status names. `year_month` ("YYYY-MM") is the report month the PCU
        table groups by."""
        pcu = pcu_responses
        stmt = (
            select(
                *pcu.c,
                func.to_char(pcu.c.report_date, "YYYY-MM").label("year_month"),
                OperationAssignation.account_id,
                CompanyAccount.name.label("account"),
                general_risk_statuses.c.name.label("risk_status"),
                general_risk_statuses.c.color.label("risk_status_color"),
            )
            .join(OperationAssignation, OperationAssignation.id == pcu.c.assignation_id)
            .join(EmployeeOperationalProfile, EmployeeOperationalProfile.id == OperationAssignation.operational_profile_id)
            .join(EmployeeRole, EmployeeRole.id == EmployeeOperationalProfile.employee_role_id)
            .outerjoin(CompanyAccount, CompanyAccount.id == OperationAssignation.account_id)
            .outerjoin(general_risk_statuses, general_risk_statuses.c.id == pcu.c.risk_status_id)
            .where(EmployeeRole.person_id == person_id)
            .order_by(pcu.c.report_date.desc().nulls_last(), pcu.c.id.desc())
        )
        return list(self._session.execute(stmt).mappings())

    def get_person_role_seniorities(self, person_id: int) -> List[RowMapping]:
        """Per role, the employee's highest technology seniority (the role comes from each
        technology's `role_id`). Retool took MAX(name) and MAX(order) separately - MAX(name)
        is alphabetical, so it could pair "Junior" with the score of "Senior"; here the name
        is the one of the highest `order`."""
        best = (
            select(
                general_roles.c.id.label("role_id"),
                general_roles.c.name.label("role_name"),
                general_seniorities.c.name.label("seniority"),
                general_seniorities.c.order.label("score"),
            )
            .select_from(EmployeeTechnology)
            .join(general_seniorities, general_seniorities.c.id == EmployeeTechnology.seniority_id)
            .join(technologies, technologies.c.id == EmployeeTechnology.technology_id)
            .join(general_roles, general_roles.c.id == technologies.c.role_id)
            .where(EmployeeTechnology.person_id == person_id)
            .ext(distinct_on(general_roles.c.id))
            .order_by(general_roles.c.id, general_seniorities.c.order.desc().nulls_last())
            .subquery()
        )
        stmt = select(best).order_by(best.c.role_name, best.c.role_id)
        return list(self._session.execute(stmt).mappings())

    def get_person_technology_seniorities(self, person_id: int, role_name: Optional[str] = None) -> List[RowMapping]:
        """The employee's technologies with seniority and role, optionally only one role
        (case-insensitive exact name - the chart sends the role it shows, so Retool's
        ILIKE '%...%' could also match longer role names that contain it)."""
        stmt = (
            select(
                technologies.c.id.label("technology_id"),
                technologies.c.name.label("tech"),
                general_seniorities.c.name.label("seniority"),
                general_seniorities.c.order.label("score"),
                general_roles.c.name.label("role_name"),
            )
            .select_from(EmployeeTechnology)
            .join(general_seniorities, general_seniorities.c.id == EmployeeTechnology.seniority_id)
            .join(technologies, technologies.c.id == EmployeeTechnology.technology_id)
            .join(general_roles, general_roles.c.id == technologies.c.role_id)
            .where(EmployeeTechnology.person_id == person_id)
            .order_by(general_roles.c.name, general_seniorities.c.order.desc().nulls_last(), technologies.c.name)
        )
        if role_name:
            stmt = stmt.where(func.lower(general_roles.c.name) == role_name.lower())
        return list(self._session.execute(stmt).mappings())

    def get_person_bill_exceptions(self, person_id: int) -> List[RowMapping]:
        """Bill exceptions of the employee's assignations, newest first."""
        be = bill_exceptions
        stmt = (
            select(
                be.c.id,
                func.concat_ws(" ", EmployeePerson.first_name, EmployeePerson.last_name).label("name"),
                be.c.exception_id,
                general_exceptions.c.name.label("exception"),
                be.c.cycle_id,
                general_cycles.c.start_date.label("cycle"),
                be.c.account_id,
                CompanyAccount.name.label("account"),
                be.c.reason_id,
                general_reasons.c.name.label("reason"),
                be.c.start_date,
                be.c.end_date,
                be.c.value,
                be.c.transactional_fee,
                be.c.approved_by,
                be.c.is_billed,
                be.c.notes,
                be.c.assignation_id,
            )
            .join(OperationAssignation, OperationAssignation.id == be.c.assignation_id)
            .join(EmployeeOperationalProfile, EmployeeOperationalProfile.id == OperationAssignation.operational_profile_id)
            .join(EmployeeRole, EmployeeRole.id == EmployeeOperationalProfile.employee_role_id)
            .join(EmployeePerson, EmployeePerson.id == EmployeeRole.person_id)
            .outerjoin(general_exceptions, general_exceptions.c.id == be.c.exception_id)
            .outerjoin(general_cycles, general_cycles.c.id == be.c.cycle_id)
            .outerjoin(CompanyAccount, CompanyAccount.id == be.c.account_id)
            .outerjoin(general_reasons, general_reasons.c.id == be.c.reason_id)
            .where(EmployeeRole.person_id == person_id)
            .order_by(be.c.start_date.desc().nulls_last(), be.c.id.desc())
        )
        return list(self._session.execute(stmt).mappings())

    def get_person_actions(self, person_id: int) -> List[RowMapping]:
        """Actions of the employee with action and status names, newest first."""
        stmt = (
            select(
                EmployeeAction.id,
                EmployeeAction.action_id,
                general_actions.c.name.label("action_name"),
                EmployeeAction.description,
                EmployeeAction.start_date,
                EmployeeAction.end_date,
                EmployeeAction.action_status_id,
                general_action_statuses.c.name.label("action_status_name"),
                EmployeeAction.is_completed,
            )
            .outerjoin(general_actions, general_actions.c.id == EmployeeAction.action_id)
            .outerjoin(general_action_statuses, general_action_statuses.c.id == EmployeeAction.action_status_id)
            .where(EmployeeAction.person_id == person_id)
            .order_by(EmployeeAction.start_date.desc().nulls_last(), EmployeeAction.id.desc())
        )
        return list(self._session.execute(stmt).mappings())

    def get_person_comments(self, person_id: int) -> List[EmployeeComment]:
        stmt = (
            select(EmployeeComment)
            .where(EmployeeComment.person_id == person_id)
            .order_by(EmployeeComment.created_at.desc(), EmployeeComment.id.desc())
        )
        return list(self._session.execute(stmt).scalars())
