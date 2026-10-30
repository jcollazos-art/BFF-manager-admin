import logging

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import v1
from app.config import Config
from app.shared.errors import AppError
from app.shared.middleware import RequestTimingMiddleware

logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="BFF Manager Admin",
    openapi_url="/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
)


def _clean_validation_message(message: str) -> str:
    return message.removeprefix("Value error, ").removeprefix("Assertion failed, ")


@app.exception_handler(AppError)
async def handle_app_error(request, exc: AppError):
    return JSONResponse(status_code=exc.status_code, content={"code": exc.code, "detail": exc.detail})


@app.exception_handler(RequestValidationError)
async def handle_validation_error(request, exc: RequestValidationError):
    errors = [
        {
            "field": ".".join(str(p) for p in e["loc"][1:]) or str(e["loc"][0]),
            "message": _clean_validation_message(e["msg"]),
            "type": e["type"],
        }
        for e in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        content={"code": "VALIDATION_ERROR", "detail": "Validation error", "errors": errors},
    )


app.add_middleware(
    CORSMiddleware,
    allow_origins=Config.CORS_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestTimingMiddleware)

app.include_router(v1.router)


@app.get("/health", tags=["Health"])
def health_check():
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
