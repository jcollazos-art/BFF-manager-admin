from fastapi import Request
from pydantic import BaseModel

from app.shared.query_filters import merge_query_filters


class FilterExample(BaseModel):
    name: str | None = None


def _request(query_string: str) -> Request:
    return Request({"type": "http", "query_string": query_string.encode(), "headers": []})


def test_declared_fields_win_over_the_raw_querystring():
    filters = merge_query_filters(_request("name=raw"), FilterExample(name="declared"))

    assert filters == {"name": "declared"}


def test_undeclared_params_are_passed_through():
    filters = merge_query_filters(_request("status=active"), FilterExample())

    assert filters == {"status": "active"}


def test_pagination_and_sort_params_are_not_filters():
    filters = merge_query_filters(_request("page=2&per_page=10&sort_field=id&sort_direction=asc"), FilterExample())

    assert filters == {}


def test_repeated_params_become_a_list():
    filters = merge_query_filters(_request("ids=1&ids=2"), FilterExample())

    assert filters == {"ids": ["1", "2"]}


def test_bracketed_values_are_parsed_as_lists():
    filters = merge_query_filters(_request("ids=[1,2,3]"), FilterExample())

    assert filters == {"ids": [1, 2, 3]}
