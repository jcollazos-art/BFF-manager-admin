"""Companies feature - for now only the tables the employee screens read. The full feature
(the Companies app migration) builds on these models; columns are mapped from the real
database (`pytest -m drift` keeps them honest).

Same convention as employee: catalog ids owned by other systems (company_id, status_id,
account_type_id, ...) are plain integer columns, no FK/relationship."""

from datetime import date, datetime
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database import Base


class CompanyAccount(Base):
    __tablename__ = "company_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[Optional[int]] = mapped_column(Integer)
    status_id: Mapped[Optional[int]] = mapped_column(Integer)
    account_type_id: Mapped[Optional[int]] = mapped_column(Integer)
    # An employee_operational_profiles.id, not a person id.
    manager_id: Mapped[Optional[int]] = mapped_column(Integer)
    name: Mapped[Optional[str]] = mapped_column(String)
    description: Mapped[Optional[str]] = mapped_column(String)
    start_date: Mapped[Optional[date]] = mapped_column(Date)
    end_date: Mapped[Optional[date]] = mapped_column(Date)
    billing_cycle: Mapped[Optional[int]] = mapped_column(Integer)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    billing_email: Mapped[Optional[str]] = mapped_column(String)
    billing_address: Mapped[Optional[str]] = mapped_column(String)
    account_category_id: Mapped[Optional[int]] = mapped_column(Integer)
    tech_partner_id: Mapped[Optional[int]] = mapped_column(Integer)
    talent_partner_id: Mapped[Optional[int]] = mapped_column(Integer)
    placement_manager_id: Mapped[Optional[int]] = mapped_column(Integer)
    account_phase_id: Mapped[Optional[int]] = mapped_column(Integer)
    last_updated_by: Mapped[Optional[str]] = mapped_column(String)
    activation_date: Mapped[Optional[date]] = mapped_column(Date)
    risk_id: Mapped[Optional[int]] = mapped_column(Integer)
    sub_account_type_id: Mapped[Optional[int]] = mapped_column(Integer)
    main_account_number: Mapped[Optional[str]] = mapped_column(String)
    placement_id: Mapped[Optional[int]] = mapped_column(Integer)
    billing_model: Mapped[Optional[str]] = mapped_column(String)


class TechnologyAccount(Base):
    """Technologies used in an account."""

    __tablename__ = "technology_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    technology_id: Mapped[Optional[int]] = mapped_column(Integer)
    account_id: Mapped[Optional[int]] = mapped_column(Integer)
    description: Mapped[Optional[str]] = mapped_column(String)
    is_main: Mapped[Optional[bool]] = mapped_column(Boolean)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    seniority_external_id: Mapped[Optional[int]] = mapped_column(Integer)
    knowledge_external_id: Mapped[Optional[int]] = mapped_column(Integer)
