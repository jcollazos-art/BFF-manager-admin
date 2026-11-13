"""Employees dashboard (the Retool employees screen: KPI cards, charts and tables). Every
endpoint takes the shared filters of DashboardFilters as query params and applies the ones
listed in its docstring. No auth yet - same note as employee/controller.py; `user_type` /
`account_type_names` are plain params until there is a logged-in user to derive them from."""

from datetime import date
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.features.employee_dashboard import custom_repository
from app.features.employee_dashboard.schemas.request import DashboardFilters
from app.features.employee_dashboard.schemas.response import (
    CostTotalsOut,
    DashboardAssignationOut,
    DashboardEmployeeOut,
    EnglishLevelCountOut,
    FinancialsOut,
    HeadcountMonthOut,
    LeavingOut,
    MainTechnologyCountOut,
    MonthlyPlRowOut,
    NewAssignationsOut,
    SeniorityCountOut,
)
from app.infrastructure.database import get_db
from app.shared.responses import Envelope

router = APIRouter(prefix="/employee/dashboard", tags=["Employee dashboard"])

Filters = Annotated[DashboardFilters, Query()]
Month = Annotated[str, Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$", description="YYYY-MM", examples=["2026-11"])]


@router.get("/english-levels", response_model=Envelope[List[EnglishLevelCountOut]])
def get_english_levels(filters: Filters, db: Session = Depends(get_db)):
    """Employees per English level. Filters: employee_ids, employees, role_ids,
    contract_type_ids, cost_center_ids, date range, account_ids, account_type_ids, manager_ids."""
    return Envelope(data=custom_repository.get_english_levels(db, filters))


@router.get("/seniorities", response_model=Envelope[List[SeniorityCountOut]])
def get_seniorities(filters: Filters, db: Session = Depends(get_db)):
    """Employees per seniority. Filters: employee_ids, employees, role_ids,
    contract_type_ids, cost_center_ids, date range, account_ids, account_type_ids, manager_ids."""
    return Envelope(data=custom_repository.get_seniorities(db, filters))


@router.get("/main-technologies", response_model=Envelope[List[MainTechnologyCountOut]])
def get_main_technologies(filters: Filters, db: Session = Depends(get_db)):
    """Top 6 principal technologies. Filters: employee_ids, employees, role_ids,
    contract_type_ids, cost_center_ids, date range, account_ids, account_type_ids, manager_ids, availability."""
    return Envelope(data=custom_repository.get_main_technologies(db, filters))


@router.get("/financials", response_model=Envelope[FinancialsOut])
def get_financials(month: Month, filters: Filters, db: Session = Depends(get_db)):
    """Revenue, profit, cost and margin of the month's billing cycle. Filters: employee_ids,
    role_ids, contract_type_ids, account_ids, account_type_ids, manager_ids, cost_center_ids,
    employees, date range, availability."""
    return Envelope(data=custom_repository.get_financials(db, filters, month))


@router.get("/cost-totals", response_model=Envelope[CostTotalsOut])
def get_cost_totals(db: Session = Depends(get_db)):
    """Real cost and cost totals of the whole cost history. No filters."""
    return Envelope(data=custom_repository.get_cost_totals(db))


@router.get("/new-assignations", response_model=Envelope[NewAssignationsOut])
def get_new_assignations(month: Month, filters: Filters, db: Session = Depends(get_db)):
    """Billable assignations starting in the month, booking vs billable. Filters: employee_ids, account_ids,
    manager_ids, cost_center_ids, role_ids, account_type_ids, contract_type_ids, include_lss, availability."""
    return Envelope(data=custom_repository.get_new_assignations(db, filters, month))


@router.get("/leaving", response_model=Envelope[LeavingOut])
def get_leaving(month: Month, filters: Filters, db: Session = Depends(get_db)):
    """Employees offboarded from an assignation in the month. Filters: employee_ids, account_ids,
    manager_ids, cost_center_ids, role_ids, account_type_ids, contract_type_ids, include_lss, availability."""
    return Envelope(data=custom_repository.get_leaving(db, filters, month))


@router.get("/headcount", response_model=Envelope[List[HeadcountMonthOut]])
def get_headcount(filters: Filters, db: Session = Depends(get_db)):
    """Employees and billable employees per month since 2019-05. Filters: all except
    user_type / account_type_names; the date range only applies with date_field."""
    return Envelope(data=custom_repository.get_headcount(db, filters))


@router.get("/employees", response_model=Envelope[List[DashboardEmployeeOut]])
def get_employees(filters: Filters, db: Session = Depends(get_db)):
    """Main table: one row per employee with their matching assignations. Filters: all except
    manager_ids and availability; without date_field only assignations not ended."""
    return Envelope(data=custom_repository.get_employees(db, filters))


@router.get("/assignations", response_model=Envelope[List[DashboardAssignationOut]])
def get_assignations(
    filters: Filters,
    reference_date: Optional[date] = Query(None, description="Month of the PCU / review flags (default today)"),
    db: Session = Depends(get_db),
):
    """One row per overlapping (position, assignation) pair. Filters: employee_ids, employees,
    contract_type_ids, account_ids, account_type_ids, manager_ids, cost_center_ids, role_ids,
    user_type (fixed account types per user type), date range."""
    return Envelope(data=custom_repository.get_assignations(db, filters, reference_date or date.today()))


@router.get("/monthly-pl", response_model=Envelope[List[MonthlyPlRowOut]])
def get_monthly_pl(month: Month, filters: Filters, db: Session = Depends(get_db)):
    """P&L of the month: (assignation, position) pairs with profit, margin, next sale price and
    managers. Filters: date range, user_type + account_type_names, employees."""
    return Envelope(data=custom_repository.get_monthly_pl(db, filters, month))
