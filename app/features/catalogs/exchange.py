"""COP exchange factor: what a COP amount (e.g. employee_positions.cost of a COP position) is
multiplied by to report it next to USD amounts. Retool loaded it on every screen with
`SELECT nominal / real AS factor FROM bill_exchange ORDER BY created_at DESC` and passed the
first row's value into each query; here the backend reads it itself, so a client never
sends it."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.features.catalogs.tables import bill_exchange
from app.shared.errors import AppError


class MissingExchangeRateError(AppError):
    status_code = 500
    code = "MISSING_EXCHANGE_RATE"
    detail = "bill_exchange has no usable rate (needs nominal and a non-zero real)"


def get_cop_factor(db: Session) -> float:
    """`nominal / real` of the newest bill_exchange row."""
    row = db.execute(
        select(bill_exchange.c.nominal, bill_exchange.c.real)
        .order_by(bill_exchange.c.created_at.desc(), bill_exchange.c.id.desc())
        .limit(1)
    ).one_or_none()
    if row is None or not row.nominal or not row.real:
        raise MissingExchangeRateError()
    return row.nominal / row.real
