from typing import List, Optional

from sqlalchemy import RowMapping

from app.features.companies.repository import CompanyRepository


def list_account_options(repo: CompanyRepository, ids: Optional[List[int]] = None) -> List[RowMapping]:
    return repo.list_account_options(ids)


def list_team_options(repo: CompanyRepository) -> List[RowMapping]:
    return repo.list_team_options()


def get_account_pocs(repo: CompanyRepository, account_id: int) -> List[RowMapping]:
    return repo.get_account_pocs(account_id)
