"""
Unit tests for ``agent_core.vector_retriever.VectorRetriever``.

These tests must NEVER hit a real Databricks workspace. The retriever is
constructed with a ``SimpleNamespace`` that exactly mimics the attributes
read off ``config.settings.Settings``, and the underlying Databricks
``VectorSearchClient`` is patched with ``unittest.mock``.

The tests cover both Stage-17 SDK behaviour
(``databricks-vectorsearch``: dict response, ``filters={...}`` kwarg,
``filters_json`` *not* used) and edge cases (filter retry on
``TypeError``, missing manifest, malformed rows, garbage scores).
"""

from __future__ import annotations

import os
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent_core.vector_retriever import (  # noqa: E402
    DEFAULT_RETURN_COLUMNS,
    REASON_DISABLED,
    REASON_MISSING_ENDPOINT,
    REASON_MISSING_HOST,
    REASON_MISSING_INDEX,
    REASON_MISSING_TOKEN,
    REASON_OK,
    REASON_OK_WITHOUT_FILTER,
    REASON_QUERY_FAILED,
    REASON_SDK_UNAVAILABLE,
    SOURCE_DATABRICKS,
    VectorRetriever,
    VectorSearchResponse,
    VectorSearchResult,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_settings(
    *,
    enabled: bool = True,
    host: str = "https://example.cloud.databricks.com",
    token: str = "dapi-test-token",
    endpoint: str = "caregrid-vector-endpoint",
    index: str = "workspace.default.caregrid_vector_index",
) -> SimpleNamespace:
    """Build a duck-typed settings stub. Production passes the real Settings()."""
    return SimpleNamespace(
        vector_search_enabled=enabled,
        databricks_host=host,
        databricks_token=token,
        vector_search_endpoint=endpoint,
        vector_search_index=index,
    )


def _dict_response(rows: list[list]) -> dict:
    """
    Build a Databricks-vectorsearch-style dict response. The score column
    is appended automatically by the index, so we mirror that here.
    """
    column_names = list(DEFAULT_RETURN_COLUMNS) + ["score"]
    return {
        "manifest": {
            "columns": [{"name": n} for n in column_names],
            "column_count": len(column_names),
        },
        "result": {
            "data_array": rows,
            "row_count": len(rows),
        },
    }


def _attach_index(retriever: VectorRetriever) -> MagicMock:
    """Bypass _get_client + _get_index by attaching a fake index directly."""
    fake_index = MagicMock(name="fake_index")
    retriever._index = fake_index
    return fake_index


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

def test_vector_search_result_defaults():
    r = VectorSearchResult(facility_id="F001")
    assert r.facility_id == "F001"
    assert r.similarity_score == 0.0
    assert r.metadata == {}
    assert r.source == SOURCE_DATABRICKS


def test_vector_search_response_defaults():
    resp = VectorSearchResponse(available=False, reason=REASON_DISABLED)
    assert resp.available is False
    assert resp.results == []
    assert resp.reason == REASON_DISABLED
    assert resp.source == SOURCE_DATABRICKS
    assert resp.filter_applied is False
    assert resp.endpoint == ""
    assert resp.index == ""


# ---------------------------------------------------------------------------
# is_available — disabled / missing env
# ---------------------------------------------------------------------------

def test_is_available_when_disabled():
    r = VectorRetriever(_make_settings(enabled=False))
    assert r.is_available() is False


def test_is_available_when_fully_configured():
    r = VectorRetriever(_make_settings())
    assert r.is_available() is True


@pytest.mark.parametrize(
    "missing_field,expected_reason",
    [
        ("host",     REASON_MISSING_HOST),
        ("token",    REASON_MISSING_TOKEN),
        ("endpoint", REASON_MISSING_ENDPOINT),
        ("index",    REASON_MISSING_INDEX),
    ],
)
def test_is_available_when_field_missing(missing_field, expected_reason):
    r = VectorRetriever(_make_settings(**{missing_field: ""}))
    assert r.is_available() is False
    resp = r.search("ICU hospitals in Mumbai")
    assert resp.available is False
    assert resp.reason == expected_reason
    assert resp.results == []
    assert resp.query == "ICU hospitals in Mumbai"


# ---------------------------------------------------------------------------
# search() — disabled path
# ---------------------------------------------------------------------------

def test_search_disabled_returns_unavailable_gracefully():
    r = VectorRetriever(_make_settings(enabled=False))
    resp = r.search("dialysis centres in Chennai")

    assert isinstance(resp, VectorSearchResponse)
    assert resp.available is False
    assert resp.reason == REASON_DISABLED
    assert resp.results == []
    assert resp.query == "dialysis centres in Chennai"


def test_search_disabled_does_not_call_databricks():
    r = VectorRetriever(_make_settings(enabled=False))
    with patch.object(VectorRetriever, "_get_index") as get_index:
        resp = r.search("anything")
    get_index.assert_not_called()
    assert resp.available is False


# ---------------------------------------------------------------------------
# search() — happy path with mocked SDK
# ---------------------------------------------------------------------------

def test_search_success_with_mocked_response():
    r = VectorRetriever(_make_settings())
    fake_index = _attach_index(r)
    fake_index.similarity_search.return_value = _dict_response([
        ["F001", "Apollo Hospital", "Maharashtra", "Mumbai", "hospital", 0.92,
         "High Trust / Evidence Supported", "Ready for recommendation", 0.987],
        ["F002", "Fortis Hospital", "Maharashtra", "Mumbai", "hospital", 0.88,
         "High Trust / Evidence Supported", "Ready for recommendation", 0.812],
        ["F003", "Lilavati Clinic", "Maharashtra", "Mumbai", "clinic", 0.71,
         "Moderate Trust / Verify Before Use", "Usable with verification", 0.654],
    ])

    resp = r.search("ICU hospital in Mumbai", num_results=3)

    assert resp.available is True
    assert resp.reason == REASON_OK
    assert resp.query == "ICU hospital in Mumbai"
    assert resp.endpoint == "caregrid-vector-endpoint"
    assert resp.index == "workspace.default.caregrid_vector_index"
    assert resp.filter_applied is False  # no filter requested
    assert len(resp.results) == 3

    first = resp.results[0]
    assert isinstance(first, VectorSearchResult)
    assert first.facility_id == "F001"
    assert first.similarity_score == pytest.approx(0.987)
    assert first.source == SOURCE_DATABRICKS
    assert first.metadata["name"] == "Apollo Hospital"
    assert first.metadata["state"] == "Maharashtra"
    assert first.metadata["trust_score"] == 0.92
    assert first.metadata["trust_category"] == "High Trust / Evidence Supported"

    # Score column must NOT leak into metadata
    assert "score" not in first.metadata

    # Similarity scores in returned order — we don't sort, we trust the index
    assert [round(r.similarity_score, 3) for r in resp.results] == [0.987, 0.812, 0.654]


def test_search_does_not_request_score_in_columns():
    """Stage 17: score is added by Databricks automatically. We must NOT
    ask for it in the columns list — the live workspace returns
    ``column not found`` if we do."""
    r = VectorRetriever(_make_settings())
    fake_index = _attach_index(r)
    fake_index.similarity_search.return_value = _dict_response([])

    r.search("anything", num_results=10)

    assert fake_index.similarity_search.called
    kwargs = fake_index.similarity_search.call_args.kwargs
    assert "score" not in kwargs["columns"]
    assert kwargs["columns"] == DEFAULT_RETURN_COLUMNS


def test_search_passes_correct_kwargs_to_sdk():
    r = VectorRetriever(_make_settings())
    fake_index = _attach_index(r)
    fake_index.similarity_search.return_value = _dict_response([])

    r.search("emergency trauma centre", num_results=15)

    fake_index.similarity_search.assert_called_once()
    kwargs = fake_index.similarity_search.call_args.kwargs
    assert kwargs["query_text"]  == "emergency trauma centre"
    assert kwargs["num_results"] == 15
    assert kwargs["columns"]     == DEFAULT_RETURN_COLUMNS
    # No filter passed → ``filters`` kwarg must be absent
    assert "filters" not in kwargs
    assert "filters_json" not in kwargs  # filters_json is never used


def test_search_with_filters_passes_python_dict():
    """Stage 17: filter is passed as a native Python dict, not JSON."""
    r = VectorRetriever(_make_settings())
    fake_index = _attach_index(r)
    fake_index.similarity_search.return_value = _dict_response([])

    resp = r.search(
        "ICU",
        filters={"state": "Bihar"},
        num_results=5,
    )

    fake_index.similarity_search.assert_called_once()
    kwargs = fake_index.similarity_search.call_args.kwargs
    assert kwargs["filters"] == {"state": "Bihar"}
    assert "filters_json" not in kwargs
    assert resp.available is True
    assert resp.filter_applied is True
    assert resp.reason == REASON_OK


def test_search_default_num_results_is_20():
    r = VectorRetriever(_make_settings())
    fake_index = _attach_index(r)
    fake_index.similarity_search.return_value = _dict_response([])

    r.search("anything")

    kwargs = fake_index.similarity_search.call_args.kwargs
    assert kwargs["num_results"] == 20


# ---------------------------------------------------------------------------
# Filter-retry behaviour (Stage 17)
# ---------------------------------------------------------------------------

def test_search_filter_typeerror_falls_back_to_no_filter():
    """If the SDK raises TypeError on ``filters=...`` (e.g. older build),
    the retriever must transparently retry without filters and mark
    ``filter_applied=False``."""
    r = VectorRetriever(_make_settings())
    fake_index = _attach_index(r)

    def side_effect(*args, **kwargs):
        if "filters" in kwargs:
            raise TypeError("similarity_search() got an unexpected keyword argument 'filters'")
        return _dict_response([
            ["F001", "Hosp", "Bihar", "Patna", "hospital", 0.85,
             "High Trust / Evidence Supported", "Ready for recommendation", 0.77],
        ])

    fake_index.similarity_search.side_effect = side_effect

    resp = r.search("ICU", filters={"state": "Bihar"}, num_results=5)

    # Two calls: first failed, second succeeded
    assert fake_index.similarity_search.call_count == 2

    first_call_kwargs  = fake_index.similarity_search.call_args_list[0].kwargs
    second_call_kwargs = fake_index.similarity_search.call_args_list[1].kwargs
    assert "filters" in first_call_kwargs
    assert "filters" not in second_call_kwargs

    assert resp.available is True
    assert resp.filter_applied is False
    assert resp.reason == REASON_OK_WITHOUT_FILTER
    assert len(resp.results) == 1
    assert resp.results[0].facility_id == "F001"


def test_search_filter_invalid_argument_falls_back_to_no_filter():
    """If the SDK raises a non-TypeError exception that mentions
    'filter', we still retry without filters."""
    r = VectorRetriever(_make_settings())
    fake_index = _attach_index(r)

    def side_effect(*args, **kwargs):
        if "filters" in kwargs:
            raise ValueError("invalid filter argument: 'state' is not a filterable column")
        return _dict_response([])

    fake_index.similarity_search.side_effect = side_effect

    resp = r.search("ICU", filters={"state": "Bihar"})

    assert fake_index.similarity_search.call_count == 2
    assert resp.available is True
    assert resp.filter_applied is False
    assert resp.reason == REASON_OK_WITHOUT_FILTER


def test_search_unfiltered_query_failure_returns_unavailable():
    """An exception not related to filters must NOT trigger a retry —
    it bubbles up as ``available=False``."""
    r = VectorRetriever(_make_settings())
    fake_index = _attach_index(r)
    fake_index.similarity_search.side_effect = RuntimeError("endpoint unreachable")

    resp = r.search("ICU")  # no filter

    assert resp.available is False
    assert resp.reason.startswith(REASON_QUERY_FAILED)
    assert "RuntimeError" in resp.reason


def test_search_no_filter_does_not_pass_filter_kwarg():
    r = VectorRetriever(_make_settings())
    fake_index = _attach_index(r)
    fake_index.similarity_search.return_value = _dict_response([])

    r.search("ICU")  # filters=None

    kwargs = fake_index.similarity_search.call_args.kwargs
    assert "filters" not in kwargs


# ---------------------------------------------------------------------------
# search() — error paths
# ---------------------------------------------------------------------------

def test_search_returns_unavailable_when_sdk_raises():
    r = VectorRetriever(_make_settings())
    fake_index = _attach_index(r)
    fake_index.similarity_search.side_effect = RuntimeError("endpoint unreachable")

    resp = r.search("ICU hospital")

    assert resp.available is False
    assert resp.results == []
    assert resp.reason.startswith(REASON_QUERY_FAILED)
    assert "RuntimeError" in resp.reason
    assert "endpoint unreachable" in resp.reason


def test_search_returns_unavailable_when_client_construction_fails():
    """A failure inside _get_client (e.g. bad credentials) must not crash."""
    r = VectorRetriever(_make_settings())
    with patch.object(
        VectorRetriever, "_get_index",
        side_effect=ConnectionError("could not reach workspace"),
    ):
        resp = r.search("ICU")
    assert resp.available is False
    assert resp.reason.startswith(REASON_QUERY_FAILED)
    assert "ConnectionError" in resp.reason


def test_search_returns_unavailable_when_sdk_not_installed():
    """Simulate ``databricks-vectorsearch`` being missing in the runtime."""
    r = VectorRetriever(_make_settings())
    with patch.object(
        VectorRetriever, "_get_index",
        side_effect=ImportError("No module named 'databricks.vector_search'"),
    ):
        resp = r.search("ICU")
    assert resp.available is False
    assert resp.reason == REASON_SDK_UNAVAILABLE


def test_search_does_not_propagate_arbitrary_exceptions():
    """Even bizarre exception types must be swallowed and reported gracefully."""
    class WeirdError(Exception):
        pass

    r = VectorRetriever(_make_settings())
    fake_index = _attach_index(r)
    fake_index.similarity_search.side_effect = WeirdError("something \n with newlines \n in it")

    resp = r.search("ICU")

    assert resp.available is False
    assert "WeirdError" in resp.reason
    # Reason must be single-line so it can go straight into a log/audit row
    assert "\n" not in resp.reason


# ---------------------------------------------------------------------------
# Response parsing edge cases
# ---------------------------------------------------------------------------

def test_parse_response_handles_empty_data_array():
    r = VectorRetriever(_make_settings())
    fake_index = _attach_index(r)
    fake_index.similarity_search.return_value = _dict_response([])

    resp = r.search("anything")

    assert resp.available is True
    assert resp.results == []


def test_parse_response_handles_missing_manifest():
    """If the SDK returns something we can't recognise, results must be empty (not crash)."""
    r = VectorRetriever(_make_settings())
    fake_index = _attach_index(r)
    fake_index.similarity_search.return_value = {"manifest": None, "result": None}

    resp = r.search("anything")

    assert resp.available is True
    assert resp.results == []


def test_parse_response_handles_legacy_namespace_shape():
    """Backward-compat: SimpleNamespace responses (from the old SDK) still parse."""
    r = VectorRetriever(_make_settings())
    fake_index = _attach_index(r)
    column_names = list(DEFAULT_RETURN_COLUMNS) + ["score"]
    columns = [SimpleNamespace(name=n) for n in column_names]
    manifest = SimpleNamespace(columns=columns, column_count=len(columns))
    rows = [
        ["F001", "Hosp", "Bihar", "Patna", "hospital", 0.5,
         "High Trust", "Ready for recommendation", 0.91],
    ]
    result = SimpleNamespace(data_array=rows, row_count=1)
    fake_index.similarity_search.return_value = SimpleNamespace(
        manifest=manifest, result=result,
    )

    resp = r.search("anything")

    assert resp.available is True
    assert len(resp.results) == 1
    assert resp.results[0].facility_id == "F001"
    assert resp.results[0].similarity_score == pytest.approx(0.91)


def test_parse_response_handles_non_numeric_score():
    """A garbage score value must not blow up — coerces to 0.0."""
    r = VectorRetriever(_make_settings())
    fake_index = _attach_index(r)
    rows = [
        ["F001", "Hosp", "MH", "Mum", "hospital", 0.5,
         "trust_cat", "ready", "not-a-number"],
    ]
    fake_index.similarity_search.return_value = _dict_response(rows)

    resp = r.search("anything")

    assert resp.available is True
    assert len(resp.results) == 1
    assert resp.results[0].similarity_score == 0.0
    assert resp.results[0].facility_id == "F001"


def test_parse_response_handles_null_score():
    r = VectorRetriever(_make_settings())
    fake_index = _attach_index(r)
    rows = [
        ["F002", "Hosp2", "KA", "BLR", "clinic", 0.7, "tc", "rr", None],
    ]
    fake_index.similarity_search.return_value = _dict_response(rows)

    resp = r.search("anything")

    assert resp.results[0].similarity_score == 0.0


def test_parse_response_skips_malformed_rows():
    """Rows whose length doesn't match the manifest are silently dropped."""
    r = VectorRetriever(_make_settings())
    fake_index = _attach_index(r)
    valid_row    = ["F001", "Hosp",  "MH", "Mum", "hospital", 0.5, "tc", "rr", 0.95]
    bad_short    = ["F002", "Hosp2"]
    bad_too_long = valid_row + ["extra"]
    fake_index.similarity_search.return_value = _dict_response([
        valid_row, bad_short, bad_too_long,
    ])

    resp = r.search("anything")

    assert resp.available is True
    assert [x.facility_id for x in resp.results] == ["F001"]


# ---------------------------------------------------------------------------
# is_available is cheap — it must not contact Databricks
# ---------------------------------------------------------------------------

def test_is_available_does_not_create_client():
    r = VectorRetriever(_make_settings())
    with patch.object(VectorRetriever, "_get_index") as get_index:
        assert r.is_available() is True
    get_index.assert_not_called()


def test_is_available_when_token_is_placeholder_passes_shape_check():
    """``is_available`` only checks for non-empty strings — a placeholder
    token still passes shape, but a real call would fail. This is by
    design: we want the retriever to attempt the call so the operator
    sees the auth error in the trace, not silently skip it."""
    r = VectorRetriever(_make_settings(token="<PASTE_TOKEN_HERE>"))
    assert r.is_available() is True


# ---------------------------------------------------------------------------
# Response unavailable — endpoint / index echoed back even on failure
# ---------------------------------------------------------------------------

def test_endpoint_and_index_echoed_back_on_unavailable_response():
    r = VectorRetriever(_make_settings(token=""))  # missing token
    resp = r.search("anything")
    assert resp.available is False
    assert resp.reason == REASON_MISSING_TOKEN
    assert resp.endpoint == "caregrid-vector-endpoint"
    assert resp.index == "workspace.default.caregrid_vector_index"


def test_endpoint_and_index_echoed_back_on_success_response():
    r = VectorRetriever(_make_settings())
    fake_index = _attach_index(r)
    fake_index.similarity_search.return_value = _dict_response([])

    resp = r.search("anything")

    assert resp.available is True
    assert resp.endpoint == "caregrid-vector-endpoint"
    assert resp.index == "workspace.default.caregrid_vector_index"
