from datetime import date
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class FilterEmployeePerson(BaseModel):
    ids: Optional[List[int]] = None
    identification: Optional[str] = None
    name_search: Optional[str] = None

    model_config = ConfigDict(extra="ignore")


class EmployeePersonUpdateItem(BaseModel):
    """PATCH /employee/persons/{id} - replaces the Retool "employee_persons: update by id"
    write, only the given fields change."""

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


class EmployeeRoleCreateItem(BaseModel):
    """POST /employee/roles - "employee_roles: insert one"."""

    person_id: int
    role_id: Optional[int] = None
    seniority_id: Optional[int] = None
    is_main: Optional[bool] = None

    model_config = ConfigDict(extra="ignore")


class EmployeeOperationalProfileCreateItem(BaseModel):
    """POST /employee/operational-profiles - "employee_operational_profiles: insert one"."""

    employee_role_id: int
    is_certified: Optional[bool] = None
    is_available: Optional[bool] = None

    model_config = ConfigDict(extra="ignore")


class EmployeeOperationalProfileBulkUpdateItem(BaseModel):
    """One item of PATCH /employee/operational-profiles/bulk - "employee_operational_profiles:
    bulk update". `id` identifies the row; best-effort per item, same savepoint idiom as
    every bulk endpoint here (see use_cases.py)."""

    id: int
    is_certified: Optional[bool] = None
    is_available: Optional[bool] = None

    model_config = ConfigDict(extra="ignore")


class EmployeePositionCreateItem(BaseModel):
    """POST /employee/positions - "employee_positions: insert one"."""

    employee_role_id: int
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


class EmployeePositionUpdateItem(BaseModel):
    """PATCH /employee/positions/{id} - "employee_positions: update one by id"."""

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


class EmployeePositionBulkUpdateItem(EmployeePositionUpdateItem):
    """One item of PATCH /employee/positions/bulk - "employee_positions: bulk update"."""

    id: int


class OperationAssignationBulkUpdateItem(BaseModel):
    """One item of PATCH /employee/assignations/bulk - "operation_assignations: bulk
    update"."""

    id: int
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


class EmployeeTechnologyCreateItem(BaseModel):
    """POST /employee/technologies - "employee_technologies: insert one"."""

    person_id: int
    seniority_id: Optional[int] = None
    technology_id: Optional[int] = None
    is_principal: Optional[bool] = None
    is_verified: Optional[bool] = None
    knowledge_external_id: Optional[int] = None
    seniority_external_id: Optional[int] = None

    model_config = ConfigDict(extra="ignore")


class EmployeeTechnologyBulkUpdateItem(BaseModel):
    """One item of PATCH /employee/technologies/bulk - "employee_technologies: bulk
    update"."""

    id: int
    seniority_id: Optional[int] = None
    technology_id: Optional[int] = None
    is_principal: Optional[bool] = None
    is_verified: Optional[bool] = None
    knowledge_external_id: Optional[int] = None
    seniority_external_id: Optional[int] = None

    model_config = ConfigDict(extra="ignore")


class EmployeeTechnologyBulkUpsertItem(BaseModel):
    """One item of POST /employee/technologies/bulk-upsert - "employee_technologies: bulk
    upsert". id present -> update; absent -> create (requires person_id)."""

    id: Optional[int] = None
    person_id: Optional[int] = None
    seniority_id: Optional[int] = None
    technology_id: Optional[int] = None
    is_principal: Optional[bool] = None
    is_verified: Optional[bool] = None
    knowledge_external_id: Optional[int] = None
    seniority_external_id: Optional[int] = None

    model_config = ConfigDict(extra="ignore")


class EmployeeLanguageCreateItem(BaseModel):
    """POST /employee/languages - "employee_languages: insert one"."""

    person_id: int
    language_id: Optional[int] = None
    language_level_id: Optional[int] = None

    model_config = ConfigDict(extra="ignore")


class EmployeeLanguageBulkUpdateItem(BaseModel):
    """One item of PATCH /employee/languages/bulk - "employee_languages: bulk update via
    primary key"."""

    id: int
    language_id: Optional[int] = None
    language_level_id: Optional[int] = None

    model_config = ConfigDict(extra="ignore")


class EmployeeEquipmentCreateItem(BaseModel):
    """POST /employee/equipments - "employee_equipments: insert one"."""

    person_id: int
    hardware_id: Optional[int] = None

    model_config = ConfigDict(extra="ignore")


class EmployeeEquipmentBulkUpdateItem(BaseModel):
    """One item of PATCH /employee/equipments/bulk - "employee_equipments: bulk update"."""

    id: int
    hardware_id: Optional[int] = None

    model_config = ConfigDict(extra="ignore")
