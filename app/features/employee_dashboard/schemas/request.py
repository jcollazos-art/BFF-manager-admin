"""Filters shared by every endpoint of the employees dashboard - the filter bar of the Retool
screen. Sent as query params (`?role_ids=3&role_ids=5&employees=all`). Each endpoint applies
the ones its Retool query applied; the endpoint's docstring lists them."""

from datetime import date
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class DashboardFilters(BaseModel):
    employee_ids: List[int] = []
    role_ids: List[int] = Field([], description="general_roles ids")
    contract_type_ids: List[int] = []
    cost_center_ids: List[int] = []
    account_ids: List[int] = []
    account_type_ids: List[int] = []
    manager_ids: List[int] = Field(
        [], description="Operational profile ids (company_accounts.manager_id) - `profile_ids` of /employee/managers/options"
    )
    employees: Literal["active", "inactive", "all"] = Field("active", description="By position status")
    availability: Literal["available", "unavailable", "all"] = Field("all", description="Operational profile is_available")
    date_field: Optional[Literal["start_date", "end_date", "effective_date"]] = Field(
        None, description="Assignation date that date_from/date_to filter (default effective_date)"
    )
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    include_lss: bool = Field(False, description="Include the 'Dedicated-LSS' P&L")
    only_started: bool = Field(False, description="Only assignations already effective")
    # Retool derived these two from the logged-in user. Parameters until there is auth.
    user_type: Optional[str] = Field(None, description="'Delivery Analyst' / 'Account Manager Lead' restrict account types")
    account_type_names: List[str] = Field([], description="Account types a restricted user_type sees")

    def sql_params(self) -> Dict[str, Any]:
        """Bind parameters for the dashboard .sql files. An empty list becomes NULL, which
        the files read as "no filter" (an empty array literal has no type in Postgres)."""
        return {key: (value or None) if isinstance(value, list) else value for key, value in self.model_dump().items()}
