from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import Config

DATABASE_URL = (
    f"{Config.DB_DRIVER}://{Config.DB_USER}:{Config.DB_PASSWORD}"
    f"@{Config.DB_HOST}:{Config.DB_PORT}/{Config.DB_NAME}"
)

engine = create_engine(
    DATABASE_URL,
    pool_size=Config.DB_POOL_SIZE,
    max_overflow=Config.DB_MAX_OVERFLOW,
    pool_timeout=Config.DB_POOL_TIMEOUT,
    pool_recycle=Config.DB_POOL_RECYCLE,
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Track A (see ARQUITECTURA_NUEVO_PROYECTO.md) - every feature's models.py declares its entities against
# this same Base, with relationship()/selectinload instead of hand-written joins per
# relation. Track B (raw SQL/Core reports) uses the engine/SessionLocal above directly and
# never needs this Base.
class Base(DeclarativeBase):
    pass


def get_db():
    """The session is the request's unit of work: repositories only execute/flush, they
    never commit. Everything the request wrote is committed once here, so a failure
    partway through a multi-step workflow rolls back everything instead of leaving earlier
    steps permanently applied."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
