"""Placeholder for the "sugar over Depends" pattern described in
ARCHITECTURA_NUEVO_PROYECTO.md section 6.3: a decorator-looking helper is fine as long as it
only wraps a Depends() and never implements the check itself.

No auth feature exists yet in this project, so `check_permission` has nothing real to check
against - it reads a plain header as a stand-in so the wiring/shape can be reviewed now,
and should be replaced with a real role lookup (off the authenticated user, once an auth
feature exists) before this is relied on for anything.
"""

from fastapi import Header, HTTPException, status


def check_permission(required_role: str):
    def dependency(x_user_role: str = Header(default="")) -> None:
        if x_user_role != required_role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires role '{required_role}'",
            )

    return dependency
