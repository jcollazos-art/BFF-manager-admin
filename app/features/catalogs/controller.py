"""No auth yet - same note as employee/controller.py."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.features.catalogs.repository import CatalogRepository
from app.features.catalogs.schemas.request import CatalogBatchRequest
from app.features.catalogs.schemas.response import CatalogBatchResponse
from app.features.catalogs.use_cases import query
from app.infrastructure.database import get_db

router = APIRouter(prefix="/catalogs", tags=["Catalogs"])


def get_repository(db: Session = Depends(get_db)) -> CatalogRepository:
    return CatalogRepository(db)


@router.post("", response_model=CatalogBatchResponse)
def get_catalogs(body: CatalogBatchRequest, repo: CatalogRepository = Depends(get_repository)):
    """Loads several catalogs in one call - POST only because the request needs a body.
    Each entry takes its own filters/page/per_page (default 20)/sort/direction/relations."""
    results = query.get_catalogs(repo, body.requests)
    return {"ok": all(result["ok"] for result in results.values()), "results": results}
