"""Compares every ORM model against the real database configured in .env (read-only).

The test container builds its tables *from* the models, so it can never notice a model that
disagrees with the real schema - e.g. `monthly_sales_price` mapped as Integer while the
column is numeric(10,2), which broke GET /details in production data. This test is the one
place that checks the models against reality. Opt-in, since it needs network access to that
database: `pytest -m drift`.
"""

import pytest
from sqlalchemy import Boolean, Date, DateTime, Float, Integer, Numeric, String, inspect
from sqlalchemy.exc import OperationalError

import app.features.catalogs.tables  # noqa: F401 - registers the tables on Base.metadata
import app.features.employee.models  # noqa: F401 - registers the tables on Base.metadata
from app.infrastructure.database import Base, engine

pytestmark = pytest.mark.drift

# Order matters: Float is a subclass of Numeric.
_CATEGORIES = [
    (Boolean, "boolean"),
    (Integer, "integer"),
    (Float, "float"),
    (Numeric, "numeric"),
    (DateTime, "datetime"),
    (Date, "date"),
    (String, "string"),
]


def _category(sql_type) -> str:
    for cls, name in _CATEGORIES:
        if isinstance(sql_type, cls):
            return name
    return type(sql_type).__name__


def test_models_match_the_real_database():
    try:
        inspector = inspect(engine)
    except OperationalError as exc:
        pytest.skip(f"real database not reachable: {exc.orig}")

    # One round trip for every table's columns - per-table calls take minutes over the network.
    real_tables = {
        table_name: {column["name"]: column["type"] for column in columns}
        for (_, table_name), columns in inspector.get_multi_columns().items()
    }

    problems = []
    for table in Base.metadata.sorted_tables:
        if table.name not in real_tables:
            problems.append(f"{table.name}: table does not exist")
            continue
        real_columns = real_tables[table.name]
        for column in table.columns:
            if column.name not in real_columns:
                problems.append(f"{table.name}.{column.name}: column does not exist")
                continue
            model_type, real_type = _category(column.type), _category(real_columns[column.name])
            if model_type != real_type:
                problems.append(
                    f"{table.name}.{column.name}: model is {model_type}, database is {real_type} ({real_columns[column.name]})"
                )

    assert not problems, "Models out of sync with the database:\n  " + "\n  ".join(problems)
