from fastapi import APIRouter

from app.features.catalogs import controller as catalogs_controller
from app.features.companies import controller as companies_controller
from app.features.employee import controller as employee_controller
from app.features.employee_dashboard import controller as employee_dashboard_controller

router = APIRouter(prefix="/v1")

router.include_router(catalogs_controller.router)
router.include_router(companies_controller.router)
router.include_router(employee_controller.router)
router.include_router(employee_dashboard_controller.router)
