"""shared/sql.py helpers, run against the test Postgres on a small inline query."""

import pytest
from sqlalchemy import text

from app.features.catalogs.tables import general_languages
from app.shared.errors import InvalidFieldError
from app.shared.sql import fetch_all, fetch_one, fetch_page
from tests.features.catalogs.factories import make_row

LANGUAGES = text("""
SELECT id, name
FROM general_languages
WHERE (:name IS NULL OR name ILIKE :name)
-- a trailing comment must not break the wrapper used by fetch_page
""")


def _page(db, **overrides):
    options = {"page": 1, "per_page": 2, "sortable": {"id", "name"}, "sort": "name", **overrides}
    return fetch_page(db, LANGUAGES, {"name": None}, **options)


@pytest.fixture
def languages(db):
    return [make_row(db, general_languages, name=name) for name in ["Spanish", "English", "German"]]


def test_fetch_one_and_fetch_all(db, languages):
    assert fetch_one(db, LANGUAGES, name="english") == {"id": languages[1]["id"], "name": "English"}
    assert fetch_one(db, LANGUAGES, name="klingon") is None
    assert [row["name"] for row in fetch_all(db, LANGUAGES, name=None)] == ["Spanish", "English", "German"]


def test_fetch_page_paginates_and_counts_with_the_filters_applied(db, languages):
    first, total = _page(db)
    second, _ = _page(db, page=2)
    filtered, filtered_total = fetch_page(
        db, LANGUAGES, {"name": "%an%"}, page=1, per_page=10, sortable={"name"}, sort="name",
    )

    assert total == 3
    assert [row["name"] for row in first] == ["English", "German"]
    assert [row["name"] for row in second] == ["Spanish"]
    assert ([row["name"] for row in filtered], filtered_total) == (["German", "Spanish"], 2)


def test_fetch_page_sorts_descending(db, languages):
    rows, _ = _page(db, direction="desc", per_page=3)

    assert [row["name"] for row in rows] == ["Spanish", "German", "English"]


def test_fetch_page_only_sorts_by_whitelisted_columns(db):
    with pytest.raises(InvalidFieldError, match="cannot sort by"):
        _page(db, sort="name; DROP TABLE general_languages")
    with pytest.raises(InvalidFieldError, match="direction"):
        _page(db, direction="asc; --")
