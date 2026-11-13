"""Read-only queries of the employees dashboard - every one is custom SQL (sql/), like
employee/custom_repository.py, and the controller calls them directly (no business logic, so
a use case would only forward the call).

Every file receives the same bind parameters: the shared filters (DashboardFilters), plus
`month`, `reference_date` and `factor` where they apply - a file ignores the ones it doesn't
use."""

from datetime import date
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.features.catalogs.exchange import get_cop_factor
from app.features.employee_dashboard.schemas.request import DashboardFilters
from app.shared.sql import Row, fetch_all, fetch_one, load_sql

_ENGLISH_LEVELS = load_sql(__file__, "english_levels")
_SENIORITIES = load_sql(__file__, "seniorities")
_MAIN_TECHNOLOGIES = load_sql(__file__, "main_technologies")
_FINANCIALS = load_sql(__file__, "financials")
_COST_TOTALS = load_sql(__file__, "cost_totals")
_NEW_ASSIGNATIONS = load_sql(__file__, "new_assignations")
_LEAVING = load_sql(__file__, "leaving")
_HEADCOUNT = load_sql(__file__, "headcount")
_EMPLOYEES = load_sql(__file__, "employees")
_ASSIGNATIONS = load_sql(__file__, "assignations")
_MONTHLY_PL = load_sql(__file__, "monthly_pl")


def _params(filters: DashboardFilters, **extra: Any) -> Dict[str, Any]:
    return {**filters.sql_params(), "month": None, "reference_date": None, "factor": None, **extra}


def get_english_levels(db: Session, filters: DashboardFilters) -> List[Row]:
    return fetch_all(db, _ENGLISH_LEVELS, **_params(filters))


def get_seniorities(db: Session, filters: DashboardFilters) -> List[Row]:
    return fetch_all(db, _SENIORITIES, **_params(filters))


def get_main_technologies(db: Session, filters: DashboardFilters) -> List[Row]:
    return fetch_all(db, _MAIN_TECHNOLOGIES, **_params(filters))


def get_financials(db: Session, filters: DashboardFilters, month: str) -> Optional[Row]:
    return fetch_one(db, _FINANCIALS, **_params(filters, month=month))


def get_cost_totals(db: Session) -> Optional[Row]:
    return fetch_one(db, _COST_TOTALS)


def get_new_assignations(db: Session, filters: DashboardFilters, month: str) -> Optional[Row]:
    return fetch_one(db, _NEW_ASSIGNATIONS, **_params(filters, month=month))


def get_leaving(db: Session, filters: DashboardFilters, month: str) -> Optional[Row]:
    return fetch_one(db, _LEAVING, **_params(filters, month=month))


def get_headcount(db: Session, filters: DashboardFilters) -> List[Row]:
    return fetch_all(db, _HEADCOUNT, **_params(filters))


def get_employees(db: Session, filters: DashboardFilters) -> List[Row]:
    return fetch_all(db, _EMPLOYEES, **_params(filters, factor=get_cop_factor(db)))


def get_assignations(db: Session, filters: DashboardFilters, reference_date: date) -> List[Row]:
    params = _params(filters, reference_date=reference_date, factor=get_cop_factor(db))
    return fetch_all(db, _ASSIGNATIONS, **params)


def get_monthly_pl(db: Session, filters: DashboardFilters, month: str) -> List[Row]:
    return fetch_all(db, _MONTHLY_PL, **_params(filters, month=month, factor=get_cop_factor(db)))
