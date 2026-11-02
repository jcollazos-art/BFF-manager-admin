"""Track A (see ARCHITECTURA_NUEVO_PROYECTO.md): declarative ORM models with relationship(),
replacing what used to be hand-written per-relation joins/subqueries plus a matching
hand-synced test Fake. All tables here live in the default ("public") schema - confirmed
against manage-admin-api's TypeORM entities (`@Entity({ name: '...' })` with no schema
option) and the raw Retool queries this module replaces, which never qualify a schema
either.

Aggregate root: EmployeePerson. Everything below it (roles -> operational_profiles/
positions -> assignations, plus technologies/languages/equipments) is a real
`ForeignKey`/`relationship()` since it belongs to this feature's own aggregate. Catalog ids
owned by other systems (role_id, seniority_id, technology_id, language_id,
language_level_id, hardware_id, contract_type_id, identification_type_id, city_id,
nationality_id, silo_id, cost_center_id, account_id, etc.) stay as plain integer columns
with no FK/relationship, same convention as bff-lsg-placement (e.g. requisitions.role_id) -
resolving their names is a catalogs-feature concern, not this one's.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, foreign, mapped_column, relationship

from app.infrastructure.database import Base


class EmployeePerson(Base):
    __tablename__ = "employee_persons"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    first_name: Mapped[Optional[str]] = mapped_column(String)
    last_name: Mapped[Optional[str]] = mapped_column(String)
    identification_type_id: Mapped[Optional[int]] = mapped_column(Integer)
    city_id: Mapped[Optional[int]] = mapped_column(Integer)
    identification: Mapped[Optional[str]] = mapped_column(String)
    photo_url: Mapped[Optional[str]] = mapped_column(String)
    nationality_id: Mapped[Optional[int]] = mapped_column(Integer)
    birth_date: Mapped[Optional[date]] = mapped_column(Date)
    phone_number: Mapped[Optional[str]] = mapped_column(String)
    personal_email: Mapped[Optional[str]] = mapped_column(String)
    corporate_email: Mapped[Optional[str]] = mapped_column(String)
    address: Mapped[Optional[str]] = mapped_column(String)
    cv_url: Mapped[Optional[str]] = mapped_column(String)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    city: Mapped[Optional["GeneralCity"]] = relationship(
        primaryjoin=lambda: foreign(EmployeePerson.city_id) == GeneralCity.id,
        viewonly=True,
        lazy="raise",
    )
    roles: Mapped[List["EmployeeRole"]] = relationship(back_populates="person", lazy="raise")
    technologies: Mapped[List["EmployeeTechnology"]] = relationship(back_populates="person", lazy="raise")
    languages: Mapped[List["EmployeeLanguage"]] = relationship(back_populates="person", lazy="raise")
    equipments: Mapped[List["EmployeeEquipment"]] = relationship(back_populates="person", lazy="raise")

    @property
    def country_id(self) -> Optional[int]:
        return self.city.country_id if self.city is not None else None


class GeneralCity(Base):
    __tablename__ = "general_cities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    country_id: Mapped[Optional[int]] = mapped_column(Integer)


class EmployeeRole(Base):
    __tablename__ = "employee_roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    person_id: Mapped[int] = mapped_column(Integer, ForeignKey("employee_persons.id"))
    role_id: Mapped[Optional[int]] = mapped_column(Integer)
    seniority_id: Mapped[Optional[int]] = mapped_column(Integer)
    is_main: Mapped[Optional[bool]] = mapped_column(Boolean)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    person: Mapped["EmployeePerson"] = relationship(back_populates="roles", lazy="raise")
    operational_profiles: Mapped[List["EmployeeOperationalProfile"]] = relationship(
        back_populates="role", lazy="raise"
    )
    positions: Mapped[List["EmployeePosition"]] = relationship(
        back_populates="role",
        order_by="desc(EmployeePosition.start_date), desc(EmployeePosition.effective_date), "
        "desc(EmployeePosition.end_date)",
        lazy="raise",
    )

    @property
    def has_active_employee_position(self) -> bool:
        return any(position.is_active for position in self.positions)


class EmployeeOperationalProfile(Base):
    __tablename__ = "employee_operational_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    employee_role_id: Mapped[int] = mapped_column(Integer, ForeignKey("employee_roles.id"))
    is_certified: Mapped[Optional[bool]] = mapped_column(Boolean)
    is_available: Mapped[Optional[bool]] = mapped_column(Boolean)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    role: Mapped["EmployeeRole"] = relationship(back_populates="operational_profiles", lazy="raise")
    assignations: Mapped[List["OperationAssignation"]] = relationship(
        back_populates="operational_profile",
        order_by="desc(OperationAssignation.start_date), desc(OperationAssignation.effective_date)",
        lazy="raise",
    )

    @property
    def has_active_employee_assignation(self) -> bool:
        today = date.today()
        return any(assignation.end_date is None or assignation.end_date > today for assignation in self.assignations)


class EmployeePosition(Base):
    __tablename__ = "employee_positions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    employee_role_id: Mapped[int] = mapped_column(Integer, ForeignKey("employee_roles.id"))
    contract_type_id: Mapped[Optional[int]] = mapped_column(Integer)
    currency: Mapped[Optional[str]] = mapped_column(String)
    start_date: Mapped[Optional[date]] = mapped_column(Date)
    end_date: Mapped[Optional[date]] = mapped_column(Date)
    salary: Mapped[Optional[Decimal]] = mapped_column(Numeric)
    additional_salary: Mapped[Optional[Decimal]] = mapped_column(Numeric)
    cost: Mapped[Optional[Decimal]] = mapped_column(Numeric)
    bonus: Mapped[Optional[Decimal]] = mapped_column(Numeric)
    is_active: Mapped[Optional[bool]] = mapped_column(Boolean)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    silo_id: Mapped[Optional[int]] = mapped_column(Integer)
    cost_center_id: Mapped[Optional[int]] = mapped_column(Integer)
    effective_date: Mapped[Optional[date]] = mapped_column(Date)
    deleted_at: Mapped[Optional[date]] = mapped_column(Date)

    role: Mapped["EmployeeRole"] = relationship(back_populates="positions", lazy="raise")

    @property
    def role_id(self) -> Optional[int]:
        return self.role.role_id

    @property
    def seniority_id(self) -> Optional[int]:
        return self.role.seniority_id


class OperationAssignation(Base):
    __tablename__ = "operation_assignations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[Optional[int]] = mapped_column(Integer)
    operational_profile_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("employee_operational_profiles.id")
    )
    allocation: Mapped[Optional[Decimal]] = mapped_column(Numeric)
    effective_date: Mapped[Optional[date]] = mapped_column(Date)
    end_date: Mapped[Optional[date]] = mapped_column(Date)
    notes: Mapped[Optional[str]] = mapped_column(String)
    is_billable: Mapped[Optional[bool]] = mapped_column(Boolean)
    monthly_sales_price: Mapped[Optional[Decimal]] = mapped_column(Numeric)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    silo_id: Mapped[Optional[int]] = mapped_column(Integer)
    cost_center_id: Mapped[Optional[int]] = mapped_column(Integer)
    start_date: Mapped[Optional[date]] = mapped_column(Date)
    reason_id: Mapped[Optional[int]] = mapped_column(Integer)
    end_reason_id: Mapped[Optional[int]] = mapped_column(Integer)
    is_onboarding: Mapped[Optional[bool]] = mapped_column(Boolean)
    is_offboarding: Mapped[Optional[bool]] = mapped_column(Boolean)
    placement_id: Mapped[Optional[str]] = mapped_column(String)
    financial_dimension_id: Mapped[Optional[int]] = mapped_column(Integer)
    payment_in_arrears: Mapped[Optional[bool]] = mapped_column(Boolean)
    po_number: Mapped[Optional[str]] = mapped_column(String)
    hourly_sales_price: Mapped[Optional[Decimal]] = mapped_column(Numeric)
    monthly_agreed_hours: Mapped[Optional[int]] = mapped_column(Integer)

    operational_profile: Mapped["EmployeeOperationalProfile"] = relationship(
        back_populates="assignations", lazy="raise"
    )

    @property
    def role_id(self) -> Optional[int]:
        return self.operational_profile.role.role_id

    @property
    def seniority_id(self) -> Optional[int]:
        return self.operational_profile.role.seniority_id


class EmployeeTechnology(Base):
    __tablename__ = "employee_technologies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    person_id: Mapped[int] = mapped_column(Integer, ForeignKey("employee_persons.id"))
    seniority_id: Mapped[Optional[int]] = mapped_column(Integer)
    technology_id: Mapped[Optional[int]] = mapped_column(Integer)
    is_principal: Mapped[Optional[bool]] = mapped_column(Boolean)
    is_verified: Mapped[Optional[bool]] = mapped_column(Boolean)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    knowledge_external_id: Mapped[Optional[int]] = mapped_column(Integer)
    seniority_external_id: Mapped[Optional[int]] = mapped_column(Integer)

    person: Mapped["EmployeePerson"] = relationship(back_populates="technologies", lazy="raise")


class EmployeeLanguage(Base):
    __tablename__ = "employee_languages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    person_id: Mapped[int] = mapped_column(Integer, ForeignKey("employee_persons.id"))
    language_id: Mapped[Optional[int]] = mapped_column(Integer)
    language_level_id: Mapped[Optional[int]] = mapped_column(Integer)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    person: Mapped["EmployeePerson"] = relationship(back_populates="languages", lazy="raise")


class EmployeeEquipment(Base):
    __tablename__ = "employee_equipments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    person_id: Mapped[int] = mapped_column(Integer, ForeignKey("employee_persons.id"))
    hardware_id: Mapped[Optional[int]] = mapped_column(Integer)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    person: Mapped["EmployeePerson"] = relationship(back_populates="equipments", lazy="raise")
