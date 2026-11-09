"""One repository per aggregate, as in employee. Only the option lists for selects for now."""

from typing import List

from sqlalchemy import RowMapping, select

from app.features.companies.models import CompanyAccount, CompanyTeam
from app.shared.repository import BaseRepository


class CompanyRepository(BaseRepository):
    def list_account_options(self) -> List[RowMapping]:
        """Every account for selects/dropdowns, by name. `end_date` and `billing_model` let the
        client hide ended accounts and pick the right price field."""
        stmt = select(
            CompanyAccount.id, CompanyAccount.name, CompanyAccount.end_date, CompanyAccount.billing_model
        ).order_by(CompanyAccount.name, CompanyAccount.id)
        return list(self._session.execute(stmt).mappings())

    def list_team_options(self) -> List[RowMapping]:
        """Every team as {id, name, account_id}, by name - for selects/dropdowns."""
        stmt = select(CompanyTeam.id, CompanyTeam.name, CompanyTeam.account_id).order_by(CompanyTeam.name, CompanyTeam.id)
        return list(self._session.execute(stmt).mappings())
