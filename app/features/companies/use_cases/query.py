from typing import List

from sqlalchemy import RowMapping

from app.features.companies.repository import CompanyRepository


def list_account_options(repo: CompanyRepository) -> List[RowMapping]:
    return repo.list_account_options()


def list_team_options(repo: CompanyRepository) -> List[RowMapping]:
    return repo.list_team_options()
