"""Test infrastructure shared by every feature. Features never touch this file - they only add
`tests/features/<feature>/` with their own factories and tests.

- A throwaway Postgres (same major version as production) is started once per run with
  testcontainers, and the tables are created from the ORM models. Only Docker is required.
- Every test runs inside a transaction that is rolled back at the end, so tests are fast,
  independent of each other, and never need cleanup.
- `client` calls the real app over HTTP; its requests share the test's session, so data
  created with factories is visible to the endpoint and vice versa.
"""

import os

from dotenv import load_dotenv

# Load the real .env first (the drift test reads that database), then fill placeholders so
# the app can be imported on a machine/CI without .env. The placeholders are never connected
# to: every test that hits the app goes through the `db` fixture below.
load_dotenv()
for key, value in {
    "DB_DRIVER": "postgresql",
    "DB_USER": "unused",
    "DB_PASSWORD": "unused",
    "DB_HOST": "localhost",
    "DB_PORT": "5432",
    "DB_NAME": "unused",
}.items():
    os.environ.setdefault(key, value)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402
from testcontainers.community.postgres import PostgresContainer  # noqa: E402

import app.features.catalogs.tables  # noqa: E402,F401 - registers the tables on Base.metadata
import app.features.companies.models  # noqa: E402,F401 - registers the tables on Base.metadata
import app.features.employee.models  # noqa: E402,F401 - registers the tables on Base.metadata
import app.features.employee_dashboard.models  # noqa: E402,F401 - registers the tables on Base.metadata
from app.infrastructure.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402

POSTGRES_IMAGE = "postgres:15-alpine"


def _require_docker() -> None:
    import docker
    from docker.errors import DockerException

    try:
        docker.from_env().ping()
    except DockerException:
        pytest.exit("Docker is not running - start Docker Desktop and run pytest again.", returncode=1)


@pytest.fixture(scope="session")
def engine():
    _require_docker()
    with PostgresContainer(POSTGRES_IMAGE, driver="psycopg2") as postgres:
        engine = create_engine(postgres.get_connection_url())
        Base.metadata.create_all(engine)
        yield engine
        engine.dispose()


@pytest.fixture
def db(engine):
    """Session bound to an outer transaction that is always rolled back. With
    `create_savepoint`, the app's own commit()/begin_nested() become SAVEPOINTs inside it,
    so the code under test behaves exactly as in production.

    `expire_on_commit=False` keeps factory-built objects readable after a request commits;
    to assert what is really stored, tests call `db.expunge_all()` and load the row again."""
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False)
    yield session
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def client(db):
    def override_get_db():
        # Same contract as app.infrastructure.database.get_db: commit on success, rollback
        # on error - both land on a SAVEPOINT of the test transaction.
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
