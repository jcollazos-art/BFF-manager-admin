from typing import Optional


class AppError(Exception):
    """`code` is a stable, machine-readable slug for the frontend to branch on; `detail` is
    the human-readable message. Keeping them separate avoids the frontend ever having to
    string-match on `detail` (see ARCHITECTURA_NUEVO_PROYECTO.md section 6.1)."""

    status_code = 400
    code = "APP_ERROR"
    detail = "Application error"

    def __init__(self, detail: Optional[str] = None, code: Optional[str] = None):
        if detail is not None:
            self.detail = detail
        if code is not None:
            self.code = code
        super().__init__(self.detail)


class NotFoundError(AppError):
    status_code = 404
    code = "NOT_FOUND"
    detail = "Resource not found"


class ConflictError(AppError):
    status_code = 409
    code = "CONFLICT"
    detail = "Conflict"


class InvalidFieldError(AppError):
    status_code = 400
    code = "INVALID_FIELD"
    detail = "Invalid field(s) requested"


def get_or_404(value, detail: str = "Resource not found"):
    if value is None:
        raise NotFoundError(detail)
    return value
