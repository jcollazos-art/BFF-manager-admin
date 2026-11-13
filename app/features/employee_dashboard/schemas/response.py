"""Output schemas of the employees dashboard - one per .sql file in ../sql, whose header
explains each field's rules."""

from datetime import date
from typing import List, Optional

from pydantic import BaseModel


class EnglishLevelCountOut(BaseModel):
    english_level: str
    employees: int


class SeniorityCountOut(BaseModel):
    seniority: Optional[str]
    employees: int


class MainTechnologyCountOut(BaseModel):
    main_tech: str
    employees: int


class FinancialsOut(BaseModel):
    """All null when nothing matched."""

    revenue: Optional[float]
    avg_revenue: Optional[float]
    profit: Optional[float]
    avg_profit: Optional[float]
    real_cost: Optional[float]
    cost: Optional[float]
    avg_real_cost: Optional[float]
    margin: Optional[float]


class CostTotalsOut(BaseModel):
    real_cost: Optional[float]
    avg_real_cost: Optional[float]
    cost: Optional[float]
    avg_cost: Optional[float]


class NewAssignationsOut(BaseModel):
    total_booking: int
    total_billable: int


class LeavingOut(BaseModel):
    total_leaving: int


class HeadcountMonthOut(BaseModel):
    year_month: str
    employees: int
    billables: int


class EmployeeAssignationItemOut(BaseModel):
    """One assignation inside DashboardEmployeeOut.assignations."""

    assignation_id: int
    account_id: Optional[int]
    account: Optional[str]
    is_billable: Optional[bool]
    is_assigned: bool
    sales_price: Optional[float]
    allocation: Optional[float]
    cost_center: Optional[str]
    profit_loss: Optional[str]
    talent_partner: Optional[str]
    tech_partner: Optional[str]
    pcu_id: Optional[int]


class DashboardEmployeeOut(BaseModel):
    """One employee of the main table - built by sql/employees.sql."""

    id: int
    fullname: str
    first_name: Optional[str]
    last_name: Optional[str]
    corporate_email: Optional[str]
    personal_email: Optional[str]
    address: Optional[str]
    identification: Optional[str]
    identification_type_id: Optional[int]
    birth_date: Optional[date]
    phone_number: Optional[str]
    city_id: Optional[int]
    country_id: Optional[int]
    position_id: int
    cost_center: Optional[str]
    contract_type: Optional[str]
    employee_cost: Optional[float]
    salary: Optional[float]
    currency: Optional[str]
    start_date: Optional[date]
    effective_date: Optional[date]
    end_date: Optional[date]
    silo_id: Optional[int]
    silo: Optional[str]
    profit_and_loss: Optional[str]
    tech_stack: Optional[str]
    language_stack: Optional[str]
    role_id: Optional[int]
    position_role: Optional[str]
    position_seniority: Optional[str]
    assignations: List[EmployeeAssignationItemOut]
    count_assignations: int
    is_billable: Optional[bool]
    sales_prices: Optional[float]
    allocations: Optional[float]
    start_date_assignation: Optional[date]
    pcu_id: Optional[int]
    employee_quality_id: Optional[int]
    assignation_id: int
    account_category_id: Optional[int]
    reason: Optional[str]
    account_manager_id: Optional[int]
    account_manager_name: Optional[str]
    account_manager_email: Optional[str]
    profile_id: int
    is_available: Optional[bool]
    is_replaced: Optional[bool]
    role: Optional[str]
    seniority: Optional[str]
    profile_match: Optional[float]
    manager: Optional[str]
    manager_email: Optional[str]
    manager_id: Optional[int]
    manager_lead: Optional[str]
    manager_lead_email: Optional[str]
    manager_lead_id: Optional[int]


class DashboardAssignationOut(BaseModel):
    """One (position, assignation) pair - built by sql/assignations.sql."""

    person_id: int
    first_name: Optional[str]
    last_name: Optional[str]
    fullname: str
    id_type: Optional[str]
    identification: Optional[str]
    corporate_email: Optional[str]
    address: Optional[str]
    tech_stack: Optional[str]
    main_tech: Optional[str]
    language_stack: Optional[str]
    employee_position_id: int
    position_employee_role_id: int
    contract_type_id: Optional[int]
    contract_type: Optional[str]
    currency: Optional[str]
    position_start_date: Optional[date]
    position_end_date: Optional[date]
    salary: Optional[float]
    employee_cost: Optional[float]
    is_active: Optional[bool]
    assignation_id: int
    assignation_employee_role_id: int
    account_id: Optional[int]
    account: Optional[str]
    billing_cycle: Optional[int]
    sales_price: Optional[float]
    is_assigned: bool
    is_billable: Optional[bool]
    allocation: Optional[float]
    assignation_effective_date: Optional[date]
    assignation_end_date: Optional[date]
    cost_center_id: Optional[int]
    cost_center: Optional[str]
    role: Optional[str]
    seniority: Optional[str]
    employee_quality_id: Optional[int]
    has_pcu: bool


class MonthlyPlRowOut(BaseModel):
    """One (assignation, position) pair of the month - built by sql/monthly_pl.sql."""

    assignation_id: int
    account_id: Optional[int]
    account: Optional[str]
    account_type_id: Optional[int]
    account_type: Optional[str]
    billing_cycle: Optional[int]
    account_manager_profile_id: Optional[int]
    account_manager_id: Optional[int]
    account_manager_name: Optional[str]
    account_manager_email: Optional[str]
    sales_price: Optional[float]
    employee_role_id: int
    employee_id: int
    fullname: str
    personal_email: Optional[str]
    email: Optional[str]
    phone_number: Optional[str]
    photo_url: Optional[str]
    address: Optional[str]
    identification: Optional[str]
    birth_date: Optional[date]
    city: Optional[str]
    country: Optional[str]
    nationality: Optional[str]
    identification_type: Optional[str]
    seniority: Optional[str]
    role: Optional[str]
    is_billable: Optional[bool]
    cost_center_id: Optional[int]
    cost_center: Optional[str]
    p_l_category: Optional[str]
    silo_name: Optional[str]
    allocation: Optional[float]
    start_date: Optional[date]
    effective_date: Optional[date]
    end_date: Optional[date]
    monthly_sales_price: Optional[float]
    position_id: int
    salary: Optional[float]
    bonus: Optional[float]
    employee_cost: Optional[float]
    currency: Optional[str]
    contract_type_id: Optional[int]
    silo_id: Optional[int]
    is_active: bool
    position_end_date: Optional[date]
    next_sale_price_date: Optional[date]
    next_sale_price: Optional[float]
    next_sale_price_caption: str
    profit: Optional[float]
    margin: Optional[float]
    manager: Optional[str]
    manager_email: Optional[str]
    manager_id: Optional[int]
    manager_lead: Optional[str]
    manager_lead_email: Optional[str]
    manager_lead_id: Optional[int]
