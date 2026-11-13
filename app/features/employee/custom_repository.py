"""Read-only repository of the employee screens for views the ORM can't express well in one
query (per-row aggregates, LATERAL, window functions): custom SQL, files in sql/. The
controller calls these directly: they have no business logic, so a use case would only
forward the call. Anything a select() with joins can build goes in repository.py instead."""

from typing import List, Optional

from sqlalchemy.orm import Session

from app.shared.sql import Row, fetch_all, fetch_one, load_sql

_PERSON_SUMMARY = load_sql(__file__, "person_summary")
_PERSON_ASSIGNATIONS = load_sql(__file__, "person_assignations")
_PERSON_TECHNOLOGY_EXPERIENCE = load_sql(__file__, "person_technology_experience")


_MANAGER_OPTIONS = load_sql(__file__, "manager_options")
_LAST_SALARY_INCREASES = load_sql(__file__, "last_salary_increases")
_MONTHLY_HEADCOUNT = load_sql(__file__, "monthly_headcount")
_PERSONS_LAST_POSITION = load_sql(__file__, "persons_last_position")


def get_manager_options(db: Session) -> List[Row]:
    return fetch_all(db, _MANAGER_OPTIONS)


def get_last_salary_increases(db: Session) -> List[Row]:
    return fetch_all(db, _LAST_SALARY_INCREASES)


def get_monthly_headcount(db: Session) -> List[Row]:
    return fetch_all(db, _MONTHLY_HEADCOUNT)


def get_persons_last_position(db: Session) -> List[Row]:
    return fetch_all(db, _PERSONS_LAST_POSITION)


def get_person_summary(db: Session, person_id: int) -> Optional[Row]:
    return fetch_one(db, _PERSON_SUMMARY, person_id=person_id)


def get_person_assignations(db: Session, person_id: int) -> List[Row]:
    return fetch_all(db, _PERSON_ASSIGNATIONS, person_id=person_id)


def get_person_technology_experience(db: Session, person_id: int) -> List[Row]:
    return fetch_all(db, _PERSON_TECHNOLOGY_EXPERIENCE, person_id=person_id)
