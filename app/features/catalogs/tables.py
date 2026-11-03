"""Core tables of the `general_*` catalogs (public schema). Generated from the real
database, not from the JSON in the architecture doc, whose types are unreliable;
`pytest -m drift` keeps them honest.

Catalogs are read generically (POST /catalogs), so they're plain `Table`s, not ORM classes.
Every one has `id` + `created_at`/`updated_at` (except `general_color_disc`); `_catalog()`
adds those, so each definition only lists its own columns. A feature that needs a catalog as
an ORM entity maps onto the same table: `class GeneralCity(Base): __table__ = general_cities`.
"""

from sqlalchemy import Boolean, Column, Date, DateTime, Float, Integer, String, Table
from sqlalchemy.dialects.postgresql import ARRAY

from app.infrastructure.database import Base


def _catalog(name: str, *columns: Column, timestamps: bool = True) -> Table:
    stamps = (Column("created_at", DateTime), Column("updated_at", DateTime)) if timestamps else ()
    return Table(name, Base.metadata, Column("id", Integer, primary_key=True), *columns, *stamps)


general_absent_status = _catalog(
    "general_absent_status",
    Column("name", String),
    Column("description", String),
)
general_absent_types = _catalog(
    "general_absent_types",
    Column("name", String),
    Column("description", String),
)
general_account_activities = _catalog(
    "general_account_activities",
    Column("name", String),
    Column("description", String),
)
general_account_activity_processes = _catalog(
    "general_account_activity_processes",
    Column("name", String),
    Column("estimated_time", Float),
    Column("is_active", Boolean),
    Column("code", String),
    Column("rule_code", String),
)
general_account_categories = _catalog(
    "general_account_categories",
    Column("name", String),
    Column("description", String),
    Column("type", String),
)
general_account_phases = _catalog(
    "general_account_phases",
    Column("name", String),
    Column("account_type_id", Integer),
    Column("account_status_id", Integer),
)
general_account_statuses = _catalog("general_account_statuses", Column("name", String))
general_account_training_types = _catalog(
    "general_account_training_types",
    Column("name", String),
    Column("description", String),
)
general_account_types = _catalog(
    "general_account_types",
    Column("name", String),
    Column("description", String),
)
general_action_plan_responsibles = _catalog(
    "general_action_plan_responsibles",
    Column("name", String),
    Column("description", String),
)
general_action_plan_types = _catalog(
    "general_action_plan_types",
    Column("name", String),
    Column("description", String),
)
general_actions = _catalog(
    "general_actions",
    Column("name", String),
    Column("type", String),
    Column("description", String),
)
general_attachment_subtype = _catalog(
    "general_attachment_subtype",
    Column("name", String),
    Column("type_id", Integer),
)
general_attachment_type = _catalog("general_attachment_type", Column("name", String))
general_augmented_services = _catalog(
    "general_augmented_services",
    Column("name", String),
    Column("description", String),
)
general_bill_account_statuses = _catalog(
    "general_bill_account_statuses",
    Column("name", String),
    Column("description", String),
)
general_business_review_topics = _catalog(
    "general_business_review_topics",
    Column("name", String),
    Column("is_system", Boolean),
)
general_ceremonies = _catalog(
    "general_ceremonies",
    Column("name", String),
    Column("description", String),
)
general_cities = _catalog("general_cities", Column("country_id", Integer), Column("name", String))
general_client_coverage_status = _catalog(
    "general_client_coverage_status",
    Column("name", String),
    Column("description", String),
)
general_color_disc = _catalog("general_color_disc", Column("name", String), timestamps=False)
general_competences = _catalog(
    "general_competences",
    Column("name", String),
    Column("type", String),
    Column("description", String),
)
general_contract_types = _catalog(
    "general_contract_types",
    Column("name", String),
    Column("is_active", Boolean),
    Column("currency", String),
)
general_cost_centers = _catalog(
    "general_cost_centers",
    Column("profit_loss_id", Integer),
    Column("name", String),
    Column("description", String),
)
general_countries = _catalog("general_countries", Column("name", String))
general_document_types = _catalog("general_document_types", Column("name", String))
general_equipments = _catalog(
    "general_equipments",
    Column("name", String),
    Column("description", String),
)
general_exception_types = _catalog("general_exception_types", Column("name", String))
general_exceptions = _catalog(
    "general_exceptions",
    Column("name", String),
    Column("description", String),
    Column("additional_charges", String),
    Column("subtract_charges", String),
    Column("exception_type_id", Integer),
)
general_financial_dimension_types = _catalog(
    "general_financial_dimension_types",
    Column("name", String),
    Column("level", String),
    Column("description", String),
)
general_flags = _catalog("general_flags", Column("order", Integer), Column("name", String))
general_frequencies = _catalog(
    "general_frequencies",
    Column("name", String),
    Column("description", String),
)
general_governance_categories = _catalog("general_governance_categories", Column("name", String))
general_governance_concept_type_values = _catalog(
    "general_governance_concept_type_values",
    Column("name", String),
    Column("concept_type_id", Integer),
)
general_governance_concept_types = _catalog(
    "general_governance_concept_types",
    Column("name", String),
    Column("is_value", Boolean),
)
general_governance_concepts = _catalog(
    "general_governance_concepts",
    Column("name", String),
    Column("description", String),
    Column("affect_billing", Boolean),
    Column("customer_visibility", Boolean),
    Column("category_id", Integer),
    Column("concept_type_id", Integer),
    Column("default_value", String),
)
general_hardwares = _catalog(
    "general_hardwares",
    Column("name", String),
    Column("hardware_ref", String),
    Column("description", String),
)
general_holidays = _catalog(
    "general_holidays",
    Column("name", String),
    Column("description", String),
    Column("holiday_date", Date),
    Column("country_code", String),
    Column("last_updated_by", String),
)
general_improvement_request_types = _catalog(
    "general_improvement_request_types",
    Column("name", String),
    Column("description", String),
)
general_industries = _catalog(
    "general_industries",
    Column("name", String),
    Column("description", String),
)
general_issue_categories = _catalog(
    "general_issue_categories",
    Column("name", String),
    Column("description", String),
)
general_issue_statuses = _catalog(
    "general_issue_statuses",
    Column("name", String),
    Column("description", String),
)
general_language_levels = _catalog(
    "general_language_levels",
    Column("name", String),
    Column("description", String),
)
general_languages = _catalog("general_languages", Column("name", String))
general_learning_platforms = _catalog("general_learning_platforms", Column("name", String))
general_manager_types = _catalog("general_manager_types", Column("name", String))
general_metrics = _catalog(
    "general_metrics",
    Column("name", String),
    Column("description", String),
    Column("deleted_at", DateTime),
)
general_newsletters = _catalog(
    "general_newsletters",
    Column("content", String),
    Column("url_link", String),
    Column("category", String),
    Column("retool_user", String),
)
general_offer_types = _catalog(
    "general_offer_types",
    Column("name", String),
    Column("description", String),
)
general_origins = _catalog(
    "general_origins",
    Column("name", String),
    Column("type", String),
    Column("description", String),
)
general_outcome_reporters = _catalog(
    "general_outcome_reporters",
    Column("name", String),
    Column("description", String),
)
general_overtime_types = _catalog(
    "general_overtime_types",
    Column("name", String),
    Column("days", ARRAY(String)),
    Column("description", String),
)
general_payment_platform = _catalog(
    "general_payment_platform",
    Column("name", String),
    Column("description", String),
)
general_payroll_novelties = _catalog(
    "general_payroll_novelties",
    Column("name", String),
    Column("description", String),
    Column("payroll_novelty_type_id", Integer),
    Column("is_deprecated", Boolean),
)
general_payroll_novelty_types = _catalog("general_payroll_novelty_types", Column("name", String))
general_placement_status = _catalog(
    "general_placement_status",
    Column("name", String),
    Column("description", String),
)
general_pmb_concept = _catalog(
    "general_pmb_concept",
    Column("name", String),
    Column("description", String),
)
general_poc_positions = _catalog(
    "general_poc_positions",
    Column("name", String),
    Column("description", String),
)
general_priorities = _catalog(
    "general_priorities",
    Column("name", String),
    Column("type", String),
    Column("description", String),
)
general_profit_and_loss = _catalog(
    "general_profit_and_loss",
    Column("name", String),
    Column("description", String),
)
general_reasons = _catalog(
    "general_reasons",
    Column("name", String),
    Column("description", String),
    Column("type", String),
)
general_recurrences = _catalog(
    "general_recurrences",
    Column("name", String),
    Column("description", String),
)
general_related_exception_and_payroll_novelty = _catalog(
    "general_related_exception_and_payroll_novelty",
    Column("exception_id", Integer),
    Column("payroll_novelty_id", Integer),
)
general_replacing_options = _catalog(
    "general_replacing_options",
    Column("name", String),
    Column("type", String),
)
general_resource_release_improvement = _catalog(
    "general_resource_release_improvement",
    Column("name", String),
)
general_resource_release_strength = _catalog(
    "general_resource_release_strength",
    Column("name", String),
)
general_retention_responsibles = _catalog(
    "general_retention_responsibles",
    Column("name", String),
    Column("description", String),
)
general_retention_statuses = _catalog(
    "general_retention_statuses",
    Column("name", String),
    Column("description", String),
)
general_review_sources = _catalog(
    "general_review_sources",
    Column("name", String),
    Column("type", String),
)
general_risk_statuses = _catalog(
    "general_risk_statuses",
    Column("name", String),
    Column("description", String),
    Column("color", String),
)
general_roles = _catalog("general_roles", Column("name", String), Column("description", String))
general_salary_request_change_types = _catalog(
    "general_salary_request_change_types",
    Column("name", String),
    Column("description", String),
)
general_salary_request_decision_makers = _catalog(
    "general_salary_request_decision_makers",
    Column("name", String),
    Column("is_active", Boolean),
    Column("description", String),
)
general_salary_request_types = _catalog(
    "general_salary_request_types",
    Column("name", String),
    Column("description", String),
)
general_seniorities = _catalog(
    "general_seniorities",
    Column("name", String),
    Column("order", Integer),
)
general_silo_types = _catalog(
    "general_silo_types",
    Column("name", String),
    Column("description", String),
)
general_silos = _catalog(
    "general_silos",
    Column("name", String),
    Column("description", String),
    Column("report_to_silo_id", Integer),
    Column("silo_type_id", Integer),
    Column("manager_id", Integer),
)
general_sub_account_types = _catalog(
    "general_sub_account_types",
    Column("name", String),
    Column("description", String),
)
general_technologies = _catalog(
    "general_technologies",
    Column("name", String),
    Column("description", String),
)
general_technology_categories = _catalog(
    "general_technology_categories",
    Column("name", String),
    Column("description", String),
)
general_technology_languages = _catalog(
    "general_technology_languages",
    Column("name", String),
    Column("description", String),
)
general_tps = _catalog("general_tps", Column("name", String), Column("description", String))
general_training_analysis_classification = _catalog(
    "general_training_analysis_classification",
    Column("name", String),
    Column("description", String),
)
general_training_attempt_link = _catalog("general_training_attempt_link", Column("name", String))
general_training_decisions = _catalog(
    "general_training_decisions",
    Column("name", String),
    Column("description", String),
)
general_training_open_positions = _catalog(
    "general_training_open_positions",
    Column("name", String),
    Column("decription", String),
)
general_training_source = _catalog(
    "general_training_source",
    Column("name", String),
    Column("description", String),
)
general_training_status = _catalog(
    "general_training_status",
    Column("name", String),
    Column("description", String),
)
general_training_workflows = _catalog("general_training_workflows", Column("name", String))
general_warrior_types = _catalog(
    "general_warrior_types",
    Column("name", String),
    Column("description", String),
)
general_work_modalities = _catalog(
    "general_work_modalities",
    Column("name", String),
    Column("decription", String),
)
