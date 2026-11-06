"""One repository per aggregate, as in employee. Only the account list for now."""

from typing import List

from sqlalchemy import RowMapping, select

from app.features.companies.models import CompanyAccount
from app.shared.repository import BaseRepository


class CompanyRepository(BaseRepository):
    def list_account_options(self) -> List[RowMapping]:
        """Every account as {id, name}, by name - for selects/dropdowns."""
        stmt = select(CompanyAccount.id, CompanyAccount.name).order_by(CompanyAccount.name, CompanyAccount.id)
        return list(self._session.execute(stmt).mappings())
