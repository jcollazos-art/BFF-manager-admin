"""Output schemas - declared once, used as `response_model=...` so FastAPI documents the
real response shape in OpenAPI and serializes straight from the ORM objects returned by
Track A's `selectinload` query (no hand-assembled dicts), per ARCHITECTURA_NUEVO_PROYECTO.md
section 6.2."""

from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class OperationAssignationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    operational_profile_id: int
    role_id: Optional[int]
    seniority_id: Optional[int]
    account_id: Optional[int]
    allocation: Optional[float]
    effective_date: Optional[date]
    end_date: Optional[date]
    notes: Optional[str]
    is_billable: Optional[bool]
    monthly_sales_price: Optional[float]
    silo_id: Optional[int]
    cost_center_id: Optional[int]
    start_date: Optional[date]
    reason_id: Optional[int]
    end_reason_id: Optional[int]
    is_onboarding: Optional[bool]
    is_offboarding: Optional[bool]
    placement_id: Optional[str]
    financial_dimension_id: Optional[int]
    payment_in_arrears: Optional[bool]
    po_number: Optional[str]
    hourly_sales_price: Optional[float]
    monthly_agreed_hours: Optional[int]


class EmployeeOperationalProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    is_certified: Optional[bool]
    is_available: Optional[bool]
    has_active_employee_assignation: bool
    assignations: List[OperationAssignationOut] = []


class EmployeePositionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    role_id: Optional[int]
    seniority_id: Optional[int]
    employee_role_id: int
    contract_type_id: Optional[int]
    currency: Optional[str]
    start_date: Optional[date]
    end_date: Optional[date]
    salary: Optional[float]
    additional_salary: Optional[float]
    cost: Optional[float]
    bonus: Optional[float]
    is_active: Optional[bool]
    silo_id: Optional[int]
    cost_center_id: Optional[int]
    effective_date: Optional[date]


class EmployeeRoleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    role_id: Optional[int]
    seniority_id: Optional[int]
    is_main: Optional[bool]
    has_active_employee_position: bool
    operational_profiles: List[EmployeeOperationalProfileOut] = []
    positions: List[EmployeePositionOut] = []


class EmployeeTechnologyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    seniority_id: Optional[int]
    technology_id: Optional[int]
    is_principal: Optional[bool]
    is_verified: Optional[bool]
    knowledge_external_id: Optional[int]
    seniority_external_id: Optional[int]


class EmployeeLanguageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    language_id: Optional[int]
    language_level_id: Optional[int]


class EmployeeEquipmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    hardware_id: Optional[int]


class EmployeePersonOut(BaseModel):
    """Flat shape for the paginated list endpoint (GET /employee/persons)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    first_name: Optional[str]
    last_name: Optional[str]
    identification_type_id: Optional[int]
    city_id: Optional[int]
    identification: Optional[str]
    photo_url: Optional[str]
    nationality_id: Optional[int]
    birth_date: Optional[datetime]
    phone_number: Optional[str]
    personal_email: Optional[str]
    corporate_email: Optional[str]
    address: Optional[str]
    cv_url: Optional[str]


class EmployeePersonDetailOut(EmployeePersonOut):
    """Nested shape for employee details - the single query (selectinload across
    the whole aggregate) that replaces the 7 separate Retool queries this module started
    from."""

    country_id: Optional[int]
    roles: List[EmployeeRoleOut] = []
    technologies: List[EmployeeTechnologyOut] = []
    languages: List[EmployeeLanguageOut] = []
    equipments: List[EmployeeEquipmentOut] = []
