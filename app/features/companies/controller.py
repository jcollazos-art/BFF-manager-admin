"""Companies feature. For now only what the employee screens need; the Companies app
migration grows this router."""

from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.features.companies.repository import CompanyRepository
from app.features.companies.schemas.response import CompanyAccountOptionOut
from app.features.companies.use_cases import query
from app.infrastructure.database import get_db
from app.shared.responses import Envelope

router = APIRouter(prefix="/companies", tags=["Companies"])


def get_repository(db: Session = Depends(get_db)) -> CompanyRepository:
    return CompanyRepository(db)


@router.get("/accounts/options", response_model=Envelope[List[CompanyAccountOptionOut]])
def get_account_options(repo: CompanyRepository = Depends(get_repository)):
    """Every account as {id, name}, by name - for selects."""
    return Envelope(data=query.list_account_options(repo))
