"""Generic CRUD every feature repository inherits: `class EmployeeRepository(BaseRepository)`.
Methods take the model class, so one repository per aggregate covers all of its child
tables; a feature only adds methods for queries with real shape (filtered listings,
eager-loaded details).

Bulk writes (`create_many`, `update_many`, `upsert_many`) are best-effort: each item runs
inside its own SAVEPOINT, so one bad item only rolls back itself, never the rest of the
batch. They return one result per item: `{"index", "ok", "id"}` or `{"index", "ok", "error"}`.
"""

from datetime import datetime
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Type, TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session, SessionTransaction

from app.infrastructure.database import Base
from app.shared.errors import InvalidFieldError, NotFoundError

M = TypeVar("M", bound=Base)

BulkResult = Dict[str, Any]


class BaseRepository:
    def __init__(self, session: Session):
        self._session = session

    # --- reads -----------------------------------------------------------------------

    def get(self, model: Type[M], row_id: int) -> Optional[M]:
        return self._session.get(model, row_id)

    def get_many(self, model: Type[M], ids: Iterable[int]) -> List[M]:
        ids = list(ids)
        if not ids:
            return []
        return list(self._session.execute(select(model).where(model.id.in_(ids))).scalars())

    def find_by(self, model: Type[M], **filters: Any) -> List[M]:
        """Equality filters only: `repo.find_by(EmployeeLanguage, person_id=10)`."""
        return list(self._session.execute(select(model).filter_by(**filters)).scalars())

    def exists(self, model: Type[Base], row_id: int) -> bool:
        return self._session.get(model, row_id) is not None

    # --- single-row writes -------------------------------------------------------------

    def create(self, model: Type[M], fields: Dict[str, Any], now: datetime) -> M:
        row = model(**fields, created_at=now, updated_at=now)
        self._session.add(row)
        self._session.flush()
        return row

    def update(self, row: Base, fields: Dict[str, Any], now: datetime) -> None:
        for key, value in fields.items():
            setattr(row, key, value)
        row.updated_at = now

    def update_by_id(self, model: Type[M], row_id: int, fields: Dict[str, Any], now: datetime) -> M:
        row = self.get(model, row_id)
        if row is None:
            raise NotFoundError(f"{model.__tablename__} id {row_id} not found")
        self.update(row, fields, now)
        return row

    def delete(self, model: Type[Base], row_id: int) -> bool:
        row = self._session.get(model, row_id)
        if row is None:
            return False
        self._session.delete(row)
        return True

    # --- bulk writes -------------------------------------------------------------------

    def create_many(self, model: Type[Base], items: Sequence[Dict[str, Any]], now: datetime) -> List[BulkResult]:
        return self._best_effort(items, lambda fields: self.create(model, fields, now).id)

    def update_many(self, model: Type[Base], items: Sequence[Dict[str, Any]], now: datetime) -> List[BulkResult]:
        """Each item must carry its `id`; the remaining keys are the fields to update."""

        def update_one(item: Dict[str, Any]) -> int:
            fields = {key: value for key, value in item.items() if key != "id"}
            return self.update_by_id(model, item["id"], fields, now).id

        return self._best_effort(items, update_one)

    def upsert_many(
        self,
        model: Type[Base],
        items: Sequence[Dict[str, Any]],
        now: datetime,
        required_on_create: Sequence[str] = (),
    ) -> List[BulkResult]:
        """Items with an `id` are updated, items without one are created. `required_on_create`
        names fields a new row can't be inserted without (e.g. its parent FK), so the item
        fails with a clear message instead of a database constraint error."""

        def upsert_one(item: Dict[str, Any]) -> int:
            fields = {key: value for key, value in item.items() if key != "id"}
            if item.get("id") is not None:
                return self.update_by_id(model, item["id"], fields, now).id
            missing = [name for name in required_on_create if fields.get(name) is None]
            if missing:
                raise InvalidFieldError(f"{model.__tablename__} requires {', '.join(missing)} to be created")
            return self.create(model, fields, now).id

        return self._best_effort(items, upsert_one)

    def delete_many(self, model: Type[Base], ids: List[int]) -> int:
        """`delete from <table> where id = ANY(...)` - a single statement, all or nothing."""
        if not ids:
            return 0
        result = self._session.execute(model.__table__.delete().where(model.id.in_(ids)))
        return result.rowcount

    # --- transactions ------------------------------------------------------------------

    def savepoint(self) -> SessionTransaction:
        """SAVEPOINT for custom best-effort loops - one bad item only rolls back itself."""
        return self._session.begin_nested()

    def _best_effort(self, items: Sequence[Dict[str, Any]], write_one: Callable[[Dict[str, Any]], int]) -> List[BulkResult]:
        results: List[BulkResult] = []
        for index, item in enumerate(items):
            savepoint = self.savepoint()
            try:
                row_id = write_one(item)
            except Exception as exc:
                savepoint.rollback()
                results.append({"index": index, "ok": False, "error": str(exc)})
            else:
                savepoint.commit()
                results.append({"index": index, "ok": True, "id": row_id})
        return results
