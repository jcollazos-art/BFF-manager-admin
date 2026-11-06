"""Every `features/*/sql/*.sql` file is planned by the test Postgres (EXPLAIN, with every
parameter NULL). Catches syntax errors and tables/columns that don't exist in the models,
for every file, without anyone writing a test for it. Behaviour is still tested through
the endpoint that uses the file."""

import pytest
from sqlalchemy import text

from app.shared.sql import all_sql_files

SQL_FILES = all_sql_files()


def test_sql_files_are_found():
    assert SQL_FILES, "no .sql files found - did features/*/sql/ move?"


@pytest.mark.parametrize("path", SQL_FILES, ids=lambda path: f"{path.parent.parent.name}/{path.name}")
def test_sql_file_is_valid(db, path):
    statement = text(path.read_text())
    db.execute(text(f"EXPLAIN {statement.text}"), {name: None for name in statement._bindparams})
