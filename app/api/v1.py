from fastapi import APIRouter

from app.features.employee import controller as employee_controller

router = APIRouter(prefix="/v1")

router.include_router(employee_controller.router)
