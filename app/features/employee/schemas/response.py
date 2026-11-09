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


class EmployeePositionRowOut(BaseModel):
    """Row of the positions table in the employee's main view - built by
    EmployeeRepository.get_person_positions."""

    id: int
    contract_type_id: Optional[int]
    currency: Optional[str]
    start_date: Optional[date]
    effective_date: Optional[date]
    end_date: Optional[date]
    salary: Optional[float]
    additional_salary: Optional[float]
    is_active: Optional[bool]
    cost: Optional[float]
    bonus: Optional[float]
    silo_id: Optional[int]
    cost_center_id: Optional[int]
    employee_role: Optional[str]
    contract_type: Optional[str]
    cost_center: Optional[str]
    seniority: Optional[str]
    silo: Optional[str]


class EmployeeTechnologyRowOut(BaseModel):
    """Row of the technologies table in the employee's main view - built by
    EmployeeRepository.get_person_technologies."""

    id: int
    person_id: int
    knowledge_external_id: Optional[int]
    seniority_external_id: Optional[int]
    is_principal: Optional[bool]
    is_verified: Optional[bool]
    seniority: Optional[str]
    score: Optional[int]


class EmployeeRoleSummaryOut(BaseModel):
    id: int
    role: Optional[str]
    seniority: Optional[str]
    is_main: Optional[bool]


class EmployeePersonSummaryOut(BaseModel):
    """Header of the employee's main view, catalog names already resolved - built by
    sql/person_summary.sql, one query."""

    employee_id: int
    fullname: str
    first_name: Optional[str]
    last_name: Optional[str]
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
    roles: List[EmployeeRoleSummaryOut]
    tech_stack: Optional[str]
    main_tech: Optional[str]
    language_stack: Optional[str]


# --- Tables of the employee's main view (GET /persons/{id}/<table>) --------------------------


class EmployeeRoleRowOut(BaseModel):
    """One row per operational profile of each role (role fields repeat)."""

    id: int
    role_id: Optional[int]
    role: Optional[str]
    seniority_id: Optional[int]
    seniority: Optional[str]
    is_main: Optional[bool]
    operational_profile_id: Optional[int]
    is_certified: Optional[bool]
    is_available: Optional[bool]


class EmployeeLanguageRowOut(BaseModel):
    id: int
    language_id: Optional[int]
    language: Optional[str]
    language_level_id: Optional[int]
    level: Optional[str]
    last_evaluation_date: Optional[datetime]


class EmployeeWarriorEvaluationOut(BaseModel):
    id: int
    employee_position_id: Optional[int]
    ew_status: Optional[str]
    last_evaluation_date: Optional[datetime]


class EmployeeAccountPersonOut(BaseModel):
    """An employee currently assigned to an account."""

    id: int
    name: str
    corporate_email: Optional[str]
    photo_url: Optional[str]


class EmployeeAccountRiskOut(BaseModel):
    """Latest PCU risk status of one account."""

    account_id: int
    account: Optional[str]
    status: Optional[str]
    color: Optional[str]


class EmployeePcuResponseOut(BaseModel):
    """One PCU response, with its account and risk status names."""

    id: int
    assignation_id: Optional[int]
    manager_id: Optional[int]
    productivity_score: Optional[int]
    motivation_score: Optional[int]
    environment_score: Optional[int]
    productivity_comment: Optional[str]
    motivation_comment: Optional[str]
    environment_comment: Optional[str]
    pending_topics: Optional[str]
    is_visible_to_customers: Optional[bool]
    report_date: Optional[date]
    year_month: Optional[str]
    account_id: Optional[int]
    account: Optional[str]
    risk_status_id: Optional[int]
    risk_status: Optional[str]
    risk_status_color: Optional[str]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]


class EmployeeQualityReportOut(BaseModel):
    """One quality report, with its account and review source names."""

    id: int
    assignation_id: Optional[int]
    english_score: Optional[float]
    tech_skill_score: Optional[float]
    engagement_score: Optional[float]
    soft_skill: Optional[float]
    date: Optional[date]
    year_month: Optional[str]
    feedback: Optional[str]
    improvement_comment: Optional[str]
    performance_issues_comment: Optional[str]
    specific_changes_comment: Optional[str]
    is_reviewed: Optional[bool]
    reviewed_by: Optional[str]
    data_origin: Optional[str]
    disabled: Optional[bool]
    external_employee_id: Optional[int]
    review_source_id: Optional[int]
    review_source: Optional[str]
    attachment: Optional[str]
    url: Optional[str]
    account_id: Optional[int]
    account: Optional[str]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]


class EmployeeAssignationRowOut(BaseModel):
    """One (assignation, overlapping position) pair - built by sql/person_assignations.sql."""

    assignation_id: int
    account_id: Optional[int]
    account: Optional[str]
    account_type_id: Optional[int]
    account_type: Optional[str]
    billing_cycle: Optional[int]
    manager_id: Optional[int]
    manager: Optional[str]
    role_id: int
    employee_id: int
    role: Optional[str]
    seniority: Optional[str]
    is_billable: Optional[bool]
    allocation: Optional[float]
    monthly_sales_price: Optional[float]
    sales_price: Optional[float]
    start_date: Optional[date]
    effective_date: Optional[date]
    end_date: Optional[date]
    po_number: Optional[str]
    cost_center_id: Optional[int]
    cost_center: Optional[str]
    p_l_category: Optional[str]
    silo_name: Optional[str]
    financial_dimension: Optional[str]
    position_id: int
    salary: Optional[float]
    employee_cost: Optional[float]
    is_active: bool
    position_end_date: Optional[date]
    margin: Optional[float]


class EmployeeTechnologyExperienceOut(BaseModel):
    """One (technology, account) pair - built by sql/person_technology_experience.sql."""

    person_id: int
    technology_id: int
    technology: Optional[str]
    type: Optional[str]
    seniority: Optional[str]
    exp_in_days: Optional[int]
    exp_in_year: float
    account_id: Optional[int]
    account: Optional[str]


class EmployeeRoleSeniorityOut(BaseModel):
    role_id: int
    role_name: Optional[str]
    seniority: Optional[str]
    score: Optional[int]


class EmployeeTechnologySeniorityOut(BaseModel):
    technology_id: int
    tech: Optional[str]
    seniority: Optional[str]
    score: Optional[int]
    role_name: Optional[str]


class EmployeeBillExceptionOut(BaseModel):
    id: int
    name: str
    exception_id: Optional[int]
    exception: Optional[str]
    cycle_id: Optional[int]
    cycle: Optional[date]
    account_id: Optional[int]
    account: Optional[str]
    reason_id: Optional[int]
    reason: Optional[str]
    start_date: Optional[date]
    end_date: Optional[date]
    value: Optional[float]
    transactional_fee: Optional[float]
    approved_by: Optional[str]
    is_billed: Optional[bool]
    notes: Optional[str]
    assignation_id: Optional[int]


class EmployeeActionOut(BaseModel):
    id: int
    action_id: Optional[int]
    action_name: Optional[str]
    description: Optional[str]
    start_date: Optional[date]
    end_date: Optional[date]
    action_status_id: Optional[int]
    action_status_name: Optional[str]
    is_completed: Optional[bool]


class EmployeeReportedCommentOut(BaseModel):
    """A comment of employee_person_comments."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    person_id: int
    comment: str
    reported_by: str
    is_active: Optional[bool]
    created_at: datetime
    updated_at: datetime


class EmployeeCommentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    comment: Optional[str]
    retool_user: Optional[str]
    created_at: Optional[datetime]
