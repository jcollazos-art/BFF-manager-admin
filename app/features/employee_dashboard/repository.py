"""ORM/Core queries of the dashboard: the ones simple enough for select(). The .sql files of
custom_repository.py hold the rest (CTEs, windows, per-row aggregates, the shared filters)."""

from sqlalchemy import Float, RowMapping, cast, func, select

from app.features.employee.models import EmployeePerson
from app.features.employee_dashboard.models import cost_employee_history
from app.shared.repository import BaseRepository


class DashboardRepository(BaseRepository):
    def get_cost_totals(self) -> RowMapping:
        """Totals of the whole cost history (every cycle): real cost and cost, summed and
        averaged per history row. No filters, as in Retool.
        Fix: each history row counts once - Retool joined it to every role of the employee, so
        an employee with two roles was summed twice (and one whose role had no role or
        seniority was left out). The join to employee_persons only keeps rows of real persons."""
        ceh = cost_employee_history.c
        real_cost, cost = func.coalesce(ceh.real_cost, 0), func.coalesce(ceh.cost, 0)
        stmt = select(
            cast(func.sum(real_cost), Float).label("real_cost"),
            cast(func.avg(real_cost), Float).label("avg_real_cost"),
            cast(func.sum(cost), Float).label("cost"),
            cast(func.avg(cost), Float).label("avg_cost"),
        ).join_from(cost_employee_history, EmployeePerson, EmployeePerson.id == ceh.person_id)
        return self._session.execute(stmt).mappings().one()
