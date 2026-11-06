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

from sqlalchemy import Boolean, Column, Date, DateTime, Float, ForeignKey, Integer, Numeric, String, Table
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, foreign, mapped_column, relationship

from app.features.catalogs.tables import general_cities
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
    actions: Mapped[List["EmployeeAction"]] = relationship(back_populates="person", lazy="raise")
    comments: Mapped[List["EmployeeComment"]] = relationship(back_populates="person", lazy="raise")

    @property
    def country_id(self) -> Optional[int]:
        return self.city.country_id if self.city is not None else None


class GeneralCity(Base):
    # The table is owned by the catalogs feature; mapped here only so the person's country
    # can be eager-loaded through `city`.
    __table__ = general_cities


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


class EmployeeAction(Base):
    __tablename__ = "employee_actions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    person_id: Mapped[int] = mapped_column(Integer, ForeignKey("employee_persons.id"))
    action_id: Mapped[Optional[int]] = mapped_column(Integer)
    action_status_id: Mapped[Optional[int]] = mapped_column(Integer)
    description: Mapped[Optional[str]] = mapped_column(String)
    start_date: Mapped[Optional[date]] = mapped_column(Date)
    end_date: Mapped[Optional[date]] = mapped_column(Date)
    is_completed: Mapped[Optional[bool]] = mapped_column(Boolean)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_by: Mapped[Optional[str]] = mapped_column(String)
    is_visible_to_customers: Mapped[Optional[bool]] = mapped_column(Boolean)
    salary_request_id: Mapped[Optional[int]] = mapped_column(Integer)
    from_customer: Mapped[Optional[bool]] = mapped_column(Boolean)
    account_id: Mapped[Optional[int]] = mapped_column(Integer)

    person: Mapped["EmployeePerson"] = relationship(back_populates="actions", lazy="raise")


class EmployeeComment(Base):
    __tablename__ = "employee_comments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    person_id: Mapped[int] = mapped_column(Integer, ForeignKey("employee_persons.id"))
    comment: Mapped[Optional[str]] = mapped_column(String)
    retool_user: Mapped[Optional[str]] = mapped_column(String)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    person: Mapped["EmployeePerson"] = relationship(back_populates="comments", lazy="raise")


# --- Tables owned by other domains, read-only here ---------------------------------------
# The employee screens read them, but they belong to modules not migrated yet (operations:
# PCU and warrior reports; billing: bill exceptions). Plain Core tables, like the catalogs:
# when their feature exists, the table moves there and these queries import it from there.

pcu_responses = Table(
    "pcu_responses",
    Base.metadata,
    Column("id", Integer, primary_key=True),
    Column("assignation_id", Integer),
    Column("manager_id", Integer),
    Column("productivity_score", Integer),
    Column("motivation_score", Integer),
    Column("environment_score", Integer),
    Column("productivity_comment", String),
    Column("motivation_comment", String),
    Column("environment_comment", String),
    Column("created_at", DateTime),
    Column("updated_at", DateTime),
    Column("report_date", Date),
    Column("pending_topics", String),
    Column("is_visible_to_customers", Boolean),
    Column("risk_status_id", Integer),
)

report_employee_warrior = Table(
    "report_employee_warrior",
    Base.metadata,
    Column("id", Integer, primary_key=True),
    Column("employee_position_id", Integer),
    Column("manager_position_id", Integer),
    Column("created_at", DateTime),
    Column("updated_at", DateTime),
    Column("avg_realization", Float),
    Column("avg_potential", Float),
    Column("warrior_type", Integer),
    Column("warrior_type_id", Integer),
)

bill_exceptions = Table(
    "bill_exceptions",
    Base.metadata,
    Column("id", Integer, primary_key=True),
    Column("reason_id", Integer),
    Column("assignation_id", Integer),
    Column("account_id", Integer),
    Column("exception_id", Integer),
    Column("frecuency_id", Integer),
    Column("cycle_id", Integer),
    Column("start_date", Date),
    Column("end_date", Date),
    Column("value", Numeric(10, 2)),
    Column("transactional_fee", Numeric(10, 2)),
    Column("total", Numeric(10, 2)),
    Column("approved_by", String),
    Column("is_billed", Boolean),
    Column("notes", String),
    Column("created_at", DateTime),
    Column("updated_at", DateTime),
    Column("declined_reason_id", Integer),
    Column("is_leader_managers_approved", Boolean),
    Column("is_backoffice_approved", Boolean),
    Column("document_support_url", String),
    Column("declination_notes", String),
    Column("created_by", String),
    Column("is_billable", Boolean),
    Column("for_billing", Boolean),
    Column("is_adjustment", Boolean),
    Column("po_number", String),
    Column("additional_info", JSONB),
    Column("team_id", Integer),
)
