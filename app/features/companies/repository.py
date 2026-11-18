"""One repository per aggregate, as in employee. Option lists for selects and the account's
client contacts for now."""

from typing import List, Optional

from sqlalchemy import RowMapping, func, select

from app.features.companies.models import AccountPoc, CompanyAccount, CompanyPoc, CompanyTeam, general_persons
from app.shared.repository import BaseRepository


class CompanyRepository(BaseRepository):
    def list_account_options(self, ids: Optional[List[int]] = None) -> List[RowMapping]:
        """Accounts for selects/dropdowns, by name - every account, or only `ids` when given.
        `end_date` and `billing_model` let the client hide ended accounts and pick the right
        price field."""
        stmt = select(
            CompanyAccount.id, CompanyAccount.name, CompanyAccount.end_date, CompanyAccount.billing_model
        ).order_by(CompanyAccount.name, CompanyAccount.id)
        if ids:
            stmt = stmt.where(CompanyAccount.id.in_(ids))
        return list(self._session.execute(stmt).mappings())

    def list_team_options(self) -> List[RowMapping]:
        """Every team as {id, name, account_id}, by name - for selects/dropdowns."""
        stmt = select(CompanyTeam.id, CompanyTeam.name, CompanyTeam.account_id).order_by(CompanyTeam.name, CompanyTeam.id)
        return list(self._session.execute(stmt).mappings())

    def get_account_pocs(self, account_id: int) -> List[RowMapping]:
        """Active client contacts of the account (account_pocs.id, name and corporate email of
        the general.persons row), by name. Soft-deleted rows (deleted_at) are left out even if
        still flagged active - Retool only checked is_active."""
        person = general_persons.c
        name = func.concat_ws(" ", person.first_name, person.last_name)
        stmt = (
            select(AccountPoc.id, name.label("name"), person.corporate_email.label("email"))
            .join(CompanyPoc, CompanyPoc.id == AccountPoc.company_poc_id)
            .join(general_persons, person.id == CompanyPoc.external_person_id)
            .where(AccountPoc.account_id == account_id, AccountPoc.is_active, AccountPoc.deleted_at.is_(None))
            .order_by(name, AccountPoc.id)
        )
        return list(self._session.execute(stmt).mappings())
