import os

from dotenv import load_dotenv

load_dotenv()


class Config:
    # DB Connection
    DB_DRIVER = os.getenv("DB_DRIVER")
    DB_USER = os.getenv("DB_USER")
    DB_PASSWORD = os.getenv("DB_PASSWORD")
    DB_HOST = os.getenv("DB_HOST")
    DB_PORT = os.getenv("DB_PORT")
    DB_NAME = os.getenv("DB_NAME")

    # Pool sizing: start conservative and raise only after checking how many connections
    # the target instance already serves for other apps (same lesson as bff-lsg-placement).
    DB_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "15"))
    DB_MAX_OVERFLOW = int(os.getenv("DB_MAX_OVERFLOW", "25"))
    DB_POOL_TIMEOUT = int(os.getenv("DB_POOL_TIMEOUT", "30"))
    DB_POOL_RECYCLE = int(os.getenv("DB_POOL_RECYCLE", "1800"))

    # CORS
    CORS_ALLOWED_ORIGINS = os.getenv(
        "CORS_ALLOWED_ORIGINS", "https://retool.com,https://*.retool.com"
    ).split(",")

    # Auth (JWT_SECRET_KEY etc.) intentionally not here yet - no auth feature exists in
    # this project yet, see shared/permissions.py and ARQUITECTURA_NUEVO_PROYECTO.md section on Depends
    # vs decorators. Add it here once a real auth feature is wired in.
