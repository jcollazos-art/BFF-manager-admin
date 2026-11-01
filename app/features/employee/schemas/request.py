from datetime import date
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class FilterEmployeePerson(BaseModel):
    ids: Optional[List[int]] = None
    identification: Optional[str] = None
    name_search: Optional[str] = None

    model_config = ConfigDict(extra="ignore")


# Every write is a bulk upsert: POST /employee/<resource>/bulk-upsert takes a list (one item
# or many). An item with `id` updates that row (only the fields sent change); an item without
# `id` creates a row, and must carry the fields named in `required_on_create` at the endpoint
# (the parent FK). Best-effort: each item runs in its own SAVEPOINT.


class EmployeePersonUpsertItem(BaseModel):
    id: Optional[int] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    identification_type_id: Optional[int] = None
    city_id: Optional[int] = None
    identification: Optional[str] = None
    photo_url: Optional[str] = None
    nationality_id: Optional[int] = None
    birth_date: Optional[date] = None
    phone_number: Optional[str] = None
    personal_email: Optional[str] = None
    corporate_email: Optional[str] = None
    address: Optional[str] = None
    cv_url: Optional[str] = None

    model_config = ConfigDict(extra="ignore")


class EmployeeRoleUpsertItem(BaseModel):
    id: Optional[int] = None
    person_id: Optional[int] = None
    role_id: Optional[int] = None
    seniority_id: Optional[int] = None
    is_main: Optional[bool] = None

    model_config = ConfigDict(extra="ignore")


class EmployeeOperationalProfileUpsertItem(BaseModel):
    id: Optional[int] = None
    employee_role_id: Optional[int] = None
    is_certified: Optional[bool] = None
    is_available: Optional[bool] = None

    model_config = ConfigDict(extra="ignore")


class EmployeePositionUpsertItem(BaseModel):
    id: Optional[int] = None
    employee_role_id: Optional[int] = None
    contract_type_id: Optional[int] = None
    currency: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    salary: Optional[Decimal] = None
    additional_salary: Optional[Decimal] = None
    cost: Optional[Decimal] = None
    bonus: Optional[Decimal] = None
    is_active: Optional[bool] = None
    silo_id: Optional[int] = None
    cost_center_id: Optional[int] = None
    effective_date: Optional[date] = None

    model_config = ConfigDict(extra="ignore")


class OperationAssignationUpsertItem(BaseModel):
    id: Optional[int] = None
    operational_profile_id: Optional[int] = None
    account_id: Optional[int] = None
    allocation: Optional[Decimal] = None
    effective_date: Optional[date] = None
    end_date: Optional[date] = None
    notes: Optional[str] = None
    is_billable: Optional[bool] = None
    monthly_sales_price: Optional[Decimal] = None
    silo_id: Optional[int] = None
    cost_center_id: Optional[int] = None
    start_date: Optional[date] = None
    reason_id: Optional[int] = None
    end_reason_id: Optional[int] = None
    is_onboarding: Optional[bool] = None
    is_offboarding: Optional[bool] = None
    placement_id: Optional[str] = None
    financial_dimension_id: Optional[int] = None
    payment_in_arrears: Optional[bool] = None
    po_number: Optional[str] = None
    hourly_sales_price: Optional[Decimal] = None
    monthly_agreed_hours: Optional[int] = None

    model_config = ConfigDict(extra="ignore")


class EmployeeTechnologyUpsertItem(BaseModel):
    id: Optional[int] = None
    person_id: Optional[int] = None
    seniority_id: Optional[int] = None
    technology_id: Optional[int] = None
    is_principal: Optional[bool] = None
    is_verified: Optional[bool] = None
    knowledge_external_id: Optional[int] = None
    seniority_external_id: Optional[int] = None

    model_config = ConfigDict(extra="ignore")


class EmployeeLanguageUpsertItem(BaseModel):
    id: Optional[int] = None
    person_id: Optional[int] = None
    language_id: Optional[int] = None
    language_level_id: Optional[int] = None

    model_config = ConfigDict(extra="ignore")


class EmployeeEquipmentUpsertItem(BaseModel):
    id: Optional[int] = None
    person_id: Optional[int] = None
    hardware_id: Optional[int] = None

    model_config = ConfigDict(extra="ignore")
