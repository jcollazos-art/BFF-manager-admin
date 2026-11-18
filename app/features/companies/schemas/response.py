from datetime import date
from typing import Optional

from pydantic import BaseModel


class CompanyAccountOptionOut(BaseModel):
    id: int
    name: Optional[str]
    end_date: Optional[date]
    billing_model: Optional[str]


class CompanyTeamOptionOut(BaseModel):
    id: int
    name: Optional[str]
    account_id: Optional[int]


class CompanyAccountPocOut(BaseModel):
    """An active client contact of an account; `id` is the account_pocs id."""

    id: int
    name: str
    email: Optional[str]
