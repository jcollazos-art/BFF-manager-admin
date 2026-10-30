"""Field-projection helper ported from bff-lsg-placement. Not wired into the employee
feature yet - it was built for hand-assembled dict responses, and sits in tension with
declaring a fixed `response_model=Page[...]` (section 6.2): a dynamic field subset doesn't
match a static Pydantic schema. Kept here, available, as an open question for the team
rather than silently picking one or the other.
"""

from app.shared.errors import InvalidFieldError  # noqa: F401 - re-exported for callers


def parse_fields(fields_str: str | None) -> dict[str, dict] | None:
    if not fields_str or not fields_str.strip():
        return None

    result: dict[str, dict] = {}
    parts = _split_top_level(fields_str)
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if "(" in part:
            name, _, nested = part.partition("(")
            name = name.strip()
            nested = nested.rstrip(")").strip()
            result[name] = parse_fields(nested) or {}
        else:
            result[part] = {}
    return result


def _split_top_level(s: str) -> list[str]:
    parts = []
    depth = 0
    current: list[str] = []
    for ch in s:
        if ch == "(":
            depth += 1
            current.append(ch)
        elif ch == ")":
            depth -= 1
            current.append(ch)
        elif ch == "," and depth == 0:
            parts.append("".join(current).strip())
            current = []
        else:
            current.append(ch)
    if current:
        parts.append("".join(current).strip())
    return parts
