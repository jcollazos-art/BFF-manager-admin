"""Tables the employees dashboard reads that belong to modules not migrated yet (billing:
bill/cost history; companies: governance models, talent/tech partners; operations: resource
releases; recruiting: skill match). Plain Core tables, read-only here, with only the columns
the dashboard uses - like the "owned by other domains" tables in employee/models.py: when
their feature exists, the table moves there and the dashboard imports it from there."""

from sqlalchemy import Boolean, Column, Date, DateTime, Integer, Numeric, String, Table

from app.infrastructure.database import Base

bill_employee_history = Table(
    "bill_employee_history",
    Base.metadata,
    Column("id", Integer, primary_key=True),
    Column("assignation_id", Integer),
    Column("person_id", Integer),
    Column("account_id", Integer),
    Column("cycle_id", Integer),
    Column("effective_date", Date),
    Column("monthly_sales_price", Numeric(10, 2)),
    Column("is_billable", Boolean),
    Column("created_at", DateTime),
    Column("updated_at", DateTime),
)

cost_employee_history = Table(
    "cost_employee_history",
    Base.metadata,
    Column("id", Integer, primary_key=True),
    Column("assignation_id", Integer),
    Column("person_id", Integer),
    Column("account_id", Integer),
    Column("cycle_id", Integer),
    Column("position_id", Integer),
    Column("real_cost", Numeric(10, 2)),
    Column("salary", Numeric(10, 2)),
    Column("cost", Numeric(10, 2)),
    Column("created_at", DateTime),
    Column("updated_at", DateTime),
)

governance_models = Table(
    "governance_models",
    Base.metadata,
    Column("id", Integer, primary_key=True),
    Column("concept_id", Integer),
    Column("account_id", Integer),
    Column("value", String),
    Column("created_at", DateTime),
    Column("updated_at", DateTime),
)

company_talent_partners = Table(
    "company_talent_partners",
    Base.metadata,
    Column("id", Integer, primary_key=True),
    Column("first_name", String),
    Column("last_name", String),
    Column("corporate_email", String),
    Column("is_active", Boolean),
    Column("created_at", DateTime),
    Column("updated_at", DateTime),
)

company_tech_partners = Table(
    "company_tech_partners",
    Base.metadata,
    Column("id", Integer, primary_key=True),
    Column("person_id", Integer),
    Column("is_active", Boolean),
    Column("created_at", DateTime),
    Column("updated_at", DateTime),
)

operation_resource_releases = Table(
    "operation_resource_releases",
    Base.metadata,
    Column("id", Integer, primary_key=True),
    Column("assignation_id", Integer),
    Column("is_replaced", Boolean),
    Column("created_at", DateTime),
    Column("updated_at", DateTime),
)

employee_skillmatch = Table(
    "employee_skillmatch",
    Base.metadata,
    Column("id", Integer, primary_key=True),
    Column("personal_email", String),
    Column("profile_match", Numeric(10, 2)),
    Column("created_at", DateTime),
    Column("updated_at", DateTime),
)
