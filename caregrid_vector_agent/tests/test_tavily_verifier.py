"""Tests for agent_core.tavily_verifier (Stage 12).

All tests stub the Tavily client through ``client_factory`` so the real
``tavily-python`` SDK is never invoked and no network call is made.
"""

import os
import sys
import time
from types import SimpleNamespace
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from agent_core.schemas import WebVerificationResult
from agent_core.tavily_cache import TavilyCache
from agent_core.tavily_verifier import (
    DEPTH_ADVANCED,
    DEPTH_BASIC,
    DEPTH_DEMO,
    REASON_API_ERROR,
    REASON_DISABLED,
    REASON_MISSING_KEY,
    REASON_SDK_UNAVAILABLE,
    VERIFICATION_ERROR,
    VERIFICATION_PARTIAL,
    VERIFICATION_SKIPPED,
    VERIFICATION_UNVERIFIED,
    VERIFICATION_VERIFIED,
    verify_facility,
    verify_facility_web_presence,
    verify_top_recommendations,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _settings(enabled: bool = True, api_key: str = "key-test"):
    return SimpleNamespace(
        tavily_enabled=enabled,
        tavily_api_key=api_key,
        tavily_default_depth="basic",
        tavily_max_web_verified=3,
    )


def _fresh_cache() -> TavilyCache:
    return TavilyCache(ttl_seconds=3600)


def _strong_search_response(name="Apollo Hospitals", city="Mumbai", state="Maharashtra"):
    """Tavily-shaped response that should score as 'verified'."""
    return {
        "results": [
            {
                "title": f"{name} — Multispecialty Hospital",
                "url": f"https://www.{name.lower().replace(' ', '')}.com/about",
                "content": (
                    f"{name} in {city}, {state} provides ICU, dialysis, "
                    f"emergency, oncology, and surgery."
                ),
                "score": 0.95,
            },
            {
                "title": f"{name} {city} reviews",
                "url": "https://www.justdial.com/Mumbai/Apollo-Hospitals",
                "content": f"User reviews of {name}.",
                "score": 0.55,
            },
        ],
        "answer": "",
    }


def _no_match_response():
    return {
        "results": [
            {
                "title": "Unrelated wellness clinic",
                "url": "https://example.com/wellness",
                "content": "A wellness retreat in Goa.",
                "score": 0.3,
            },
        ],
        "answer": "",
    }


def _make_client(response):
    """Return a MagicMock Tavily client whose `.search()` always returns `response`."""
    client = MagicMock()
    client.search.return_value = response
    return client


def _factory_for(client):
    """Build a `client_factory(api_key)` that returns the given client."""
    factory = MagicMock(return_value=client)
    return factory


# ---------------------------------------------------------------------------
# 1. Disabled / missing-key paths
# ---------------------------------------------------------------------------

def test_disabled_returns_skipped_and_does_not_call_factory():
    factory = MagicMock()
    s = _settings(enabled=False, api_key="key-test")
    res = verify_facility_web_presence(
        "Apollo Hospitals", "Mumbai", "Maharashtra",
        settings=s, cache=_fresh_cache(), client_factory=factory,
    )
    assert isinstance(res, WebVerificationResult)
    assert res.verification_status == VERIFICATION_SKIPPED
    assert res.web_checked is False
    assert res.web_available is False
    assert REASON_DISABLED in res.verification_notes
    factory.assert_not_called()


def test_missing_api_key_returns_skipped_and_does_not_call_factory():
    factory = MagicMock()
    s = _settings(enabled=True, api_key="")
    res = verify_facility_web_presence(
        "Apollo Hospitals", "Mumbai", "Maharashtra",
        settings=s, cache=_fresh_cache(), client_factory=factory,
    )
    assert res.verification_status == VERIFICATION_SKIPPED
    assert REASON_MISSING_KEY in res.verification_notes
    factory.assert_not_called()


def test_missing_api_key_does_not_crash_with_default_settings():
    """The original spec test: agent must survive a missing key without raising."""
    s = _settings(enabled=True, api_key=None)  # type: ignore[arg-type]
    res = verify_facility_web_presence(
        "Some Hospital", "Pune", "Maharashtra",
        settings=s, cache=_fresh_cache(),
    )
    assert isinstance(res, WebVerificationResult)
    assert res.verification_status == VERIFICATION_SKIPPED


def test_unknown_depth_falls_back_to_basic():
    client = _make_client(_strong_search_response())
    factory = _factory_for(client)
    res = verify_facility_web_presence(
        "Apollo Hospitals", "Mumbai", "Maharashtra",
        depth="weird-depth",
        settings=_settings(), cache=_fresh_cache(), client_factory=factory,
    )
    # Only one search call (basic), search_depth='basic'.
    assert client.search.call_count == 1
    assert client.search.call_args.kwargs["search_depth"] == "basic"
    assert res.verification_status in {
        VERIFICATION_VERIFIED, VERIFICATION_PARTIAL,
    }


# ---------------------------------------------------------------------------
# 2. Mocked-success path mapping
# ---------------------------------------------------------------------------

def test_mocked_successful_search_maps_to_verified():
    client = _make_client(_strong_search_response())
    factory = _factory_for(client)
    res = verify_facility_web_presence(
        "Apollo Hospitals", "Mumbai", "Maharashtra",
        requested_capabilities=["ICU", "dialysis"],
        depth=DEPTH_BASIC,
        facility_id="F001",
        settings=_settings(), cache=_fresh_cache(), client_factory=factory,
    )

    assert res.facility_id == "F001"
    assert res.verification_status == VERIFICATION_VERIFIED
    assert res.web_checked is True
    assert res.web_available is True
    assert res.matched_name == "Apollo Hospitals"
    assert "Mumbai" in res.matched_location
    assert "Maharashtra" in res.matched_location
    assert {"icu", "dialysis"}.issubset(set(res.matched_capability))
    assert res.top_url.startswith("https://")
    assert res.top_snippet
    assert res.verification_score >= 0.7
    assert res.error_message is None
    assert res.credits_estimated == 1  # one basic call
    assert any("Name match" in n for n in res.verification_notes)
    assert res.cached is False


def test_no_results_returns_unverified_but_web_available():
    client = _make_client({"results": []})
    factory = _factory_for(client)
    res = verify_facility_web_presence(
        "Tiny Clinic", "Indore", "Madhya Pradesh",
        settings=_settings(), cache=_fresh_cache(), client_factory=factory,
    )
    assert res.verification_status == VERIFICATION_UNVERIFIED
    assert res.web_checked is True
    assert res.web_available is True  # we did call the API
    assert res.verification_score == 0.0
    assert res.matched_name == ""
    assert res.matched_location == ""


def test_results_without_match_returns_unverified():
    client = _make_client(_no_match_response())
    factory = _factory_for(client)
    res = verify_facility_web_presence(
        "Apollo Hospitals", "Mumbai", "Maharashtra",
        settings=_settings(), cache=_fresh_cache(), client_factory=factory,
    )
    assert res.verification_status == VERIFICATION_UNVERIFIED
    assert res.verification_score < 0.4


def test_partial_match_only_name_returns_partial():
    response = {
        "results": [{
            "title": "Apollo Hospitals — Multispecialty",
            "url": "https://example.com",
            "content": "Apollo Hospitals provides various services.",
        }],
    }
    client = _make_client(response)
    factory = _factory_for(client)
    res = verify_facility_web_presence(
        "Apollo Hospitals", "Mumbai", "Maharashtra",
        settings=_settings(), cache=_fresh_cache(), client_factory=factory,
    )
    assert res.verification_status == VERIFICATION_PARTIAL
    assert 0.4 <= res.verification_score < 0.7
    assert res.matched_name == "Apollo Hospitals"
    assert res.matched_location == ""


# ---------------------------------------------------------------------------
# 3. Cache behaviour
# ---------------------------------------------------------------------------

def test_cache_prevents_duplicate_call():
    client = _make_client(_strong_search_response())
    factory = _factory_for(client)
    cache = _fresh_cache()
    s = _settings()

    res1 = verify_facility_web_presence(
        "Apollo Hospitals", "Mumbai", "Maharashtra",
        settings=s, cache=cache, client_factory=factory,
    )
    res2 = verify_facility_web_presence(
        "Apollo Hospitals", "Mumbai", "Maharashtra",
        settings=s, cache=cache, client_factory=factory,
    )

    assert client.search.call_count == 1, "second call should be served from cache"
    assert res1.cached is False
    assert res2.cached is True
    # Body is identical otherwise.
    assert res2.facility_id == res1.facility_id
    assert res2.verification_score == res1.verification_score


def test_cache_hit_overrides_facility_id_with_caller_value():
    """Two callers may share name/city/state/depth but use different
    canonical ``facility_id``s. The cached result must carry the
    *caller's* ID — otherwise downstream mapping by ``facility_id``
    breaks (regression for golden-query / engine cross-test pollution).
    """
    client = _make_client(_strong_search_response())
    factory = _factory_for(client)
    cache = _fresh_cache()
    s = _settings()

    res_a = verify_facility_web_presence(
        "Apollo Hospitals", "Mumbai", "Maharashtra",
        facility_id="F-A", settings=s, cache=cache, client_factory=factory,
    )
    res_b = verify_facility_web_presence(
        "Apollo Hospitals", "Mumbai", "Maharashtra",
        facility_id="F-B", settings=s, cache=cache, client_factory=factory,
    )

    assert client.search.call_count == 1, "second call should be served from cache"
    assert res_a.facility_id == "F-A"
    assert res_b.facility_id == "F-B"
    assert res_b.cached is True
    # Verification body must be identical even though the IDs differ.
    assert res_b.verification_score == res_a.verification_score
    assert res_b.top_url == res_a.top_url


def test_cache_key_distinguishes_depth():
    client = _make_client(_strong_search_response())
    factory = _factory_for(client)
    cache = _fresh_cache()
    s = _settings()

    verify_facility_web_presence(
        "Apollo Hospitals", "Mumbai", "Maharashtra",
        depth=DEPTH_BASIC, settings=s, cache=cache, client_factory=factory,
    )
    verify_facility_web_presence(
        "Apollo Hospitals", "Mumbai", "Maharashtra",
        depth=DEPTH_ADVANCED, settings=s, cache=cache, client_factory=factory,
    )
    # Basic = 1 call, Advanced = 2 calls (facility + capability) -> 3 total.
    # But no capabilities supplied here, so advanced collapses to 1 call.
    # Expect at least 2 calls because cache key differs by depth.
    assert client.search.call_count >= 2


def test_cache_key_distinguishes_capabilities():
    client = _make_client(_strong_search_response())
    factory = _factory_for(client)
    cache = _fresh_cache()
    s = _settings()

    verify_facility_web_presence(
        "Apollo Hospitals", "Mumbai", "Maharashtra",
        requested_capabilities=["ICU"],
        settings=s, cache=cache, client_factory=factory,
    )
    verify_facility_web_presence(
        "Apollo Hospitals", "Mumbai", "Maharashtra",
        requested_capabilities=["dialysis"],
        settings=s, cache=cache, client_factory=factory,
    )
    assert client.search.call_count == 2


def test_cache_capabilities_order_does_not_matter():
    """Same capabilities in a different order must hit the same cache entry."""
    client = _make_client(_strong_search_response())
    factory = _factory_for(client)
    cache = _fresh_cache()
    s = _settings()

    verify_facility_web_presence(
        "Apollo Hospitals", "Mumbai", "Maharashtra",
        requested_capabilities=["ICU", "dialysis"],
        settings=s, cache=cache, client_factory=factory,
    )
    res2 = verify_facility_web_presence(
        "Apollo Hospitals", "Mumbai", "Maharashtra",
        requested_capabilities=["dialysis", "ICU"],
        settings=s, cache=cache, client_factory=factory,
    )
    assert client.search.call_count == 1
    assert res2.cached is True


def test_cache_ttl_expires_entry():
    cache = TavilyCache(ttl_seconds=1)
    client = _make_client(_strong_search_response())
    factory = _factory_for(client)
    s = _settings()

    verify_facility_web_presence(
        "Apollo Hospitals", "Mumbai", "Maharashtra",
        settings=s, cache=cache, client_factory=factory,
    )
    assert cache.size() == 1
    time.sleep(1.1)
    res = verify_facility_web_presence(
        "Apollo Hospitals", "Mumbai", "Maharashtra",
        settings=s, cache=cache, client_factory=factory,
    )
    assert res.cached is False
    assert client.search.call_count == 2


def test_cache_make_key_is_deterministic_and_normalised():
    a = TavilyCache.make_key(" Apollo ", "Mumbai", "Maharashtra", ["ICU", "Dialysis"], "BASIC")
    b = TavilyCache.make_key("apollo", " mumbai", "maharashtra ", ["dialysis", "icu"], "basic")
    assert a == b


# ---------------------------------------------------------------------------
# 4. Depth behaviour
# ---------------------------------------------------------------------------

def test_basic_depth_makes_one_call_and_uses_basic_search_depth():
    client = _make_client(_strong_search_response())
    factory = _factory_for(client)
    res = verify_facility_web_presence(
        "Apollo Hospitals", "Mumbai", "Maharashtra",
        requested_capabilities=["ICU", "dialysis"],
        depth=DEPTH_BASIC,
        settings=_settings(), cache=_fresh_cache(), client_factory=factory,
    )
    assert client.search.call_count == 1
    kwargs = client.search.call_args.kwargs
    assert kwargs["search_depth"] == "basic"
    assert kwargs["max_results"] == 5
    assert "Apollo Hospitals" in kwargs["query"]
    assert "Mumbai" in kwargs["query"]
    assert res.credits_estimated == 1


def test_advanced_depth_makes_two_calls_when_capabilities_given():
    client = _make_client(_strong_search_response())
    factory = _factory_for(client)
    res = verify_facility_web_presence(
        "Apollo Hospitals", "Mumbai", "Maharashtra",
        requested_capabilities=["ICU", "dialysis"],
        depth=DEPTH_ADVANCED,
        settings=_settings(), cache=_fresh_cache(), client_factory=factory,
    )
    assert client.search.call_count == 2
    for call in client.search.call_args_list:
        assert call.kwargs["search_depth"] == "advanced"
    # Second query should include capability tokens.
    second_query = client.search.call_args_list[1].kwargs["query"].lower()
    assert "icu" in second_query
    assert "dialysis" in second_query
    assert res.credits_estimated == 4  # 2 advanced calls × 2 credits each


def test_advanced_depth_collapses_to_one_call_without_capabilities():
    client = _make_client(_strong_search_response())
    factory = _factory_for(client)
    res = verify_facility_web_presence(
        "Apollo Hospitals", "Mumbai", "Maharashtra",
        depth=DEPTH_ADVANCED,
        settings=_settings(), cache=_fresh_cache(), client_factory=factory,
    )
    assert client.search.call_count == 1
    assert res.credits_estimated == 2


def test_demo_depth_extracts_official_looking_url():
    response = {
        "results": [
            {
                "title": "Apollo Hospitals — JustDial",
                "url": "https://www.justdial.com/Mumbai/Apollo-Hospitals",
                "content": "Apollo Hospitals Mumbai Maharashtra ICU dialysis listing.",
            },
            {
                "title": "Apollo Hospitals official site",
                "url": "https://www.apollohospitals.com/locations/mumbai",
                "content": "Apollo Hospitals in Mumbai, Maharashtra. ICU and dialysis.",
            },
        ],
    }
    client = _make_client(response)
    factory = _factory_for(client)
    res = verify_facility_web_presence(
        "Apollo Hospitals", "Mumbai", "Maharashtra",
        requested_capabilities=["ICU"],
        depth=DEPTH_DEMO,
        settings=_settings(), cache=_fresh_cache(), client_factory=factory,
    )
    assert "apollohospitals.com" in res.top_url
    assert any("Official-looking URL" in n for n in res.verification_notes)


# ---------------------------------------------------------------------------
# 5. Error paths
# ---------------------------------------------------------------------------

def test_client_factory_raises_import_error_returns_sdk_unavailable():
    factory = MagicMock(side_effect=ImportError("tavily-python not installed"))
    res = verify_facility_web_presence(
        "Apollo Hospitals", "Mumbai", "Maharashtra",
        settings=_settings(), cache=_fresh_cache(), client_factory=factory,
    )
    assert res.verification_status == VERIFICATION_ERROR
    assert REASON_SDK_UNAVAILABLE in res.verification_notes
    assert res.error_message
    assert "tavily-python" in res.error_message


def test_client_factory_raises_other_exception_returns_error():
    factory = MagicMock(side_effect=RuntimeError("init failed"))
    res = verify_facility_web_presence(
        "Apollo Hospitals", "Mumbai", "Maharashtra",
        settings=_settings(), cache=_fresh_cache(), client_factory=factory,
    )
    assert res.verification_status == VERIFICATION_ERROR
    assert REASON_API_ERROR in res.verification_notes
    assert "RuntimeError" in (res.error_message or "")


def test_search_call_raises_returns_error_with_short_message():
    client = MagicMock()
    client.search.side_effect = ValueError("bad request")
    factory = _factory_for(client)
    res = verify_facility_web_presence(
        "Apollo Hospitals", "Mumbai", "Maharashtra",
        settings=_settings(), cache=_fresh_cache(), client_factory=factory,
    )
    assert res.verification_status == VERIFICATION_ERROR
    assert REASON_API_ERROR in res.verification_notes
    assert "\n" not in (res.error_message or "")
    assert len(res.error_message or "") <= 200


def test_search_returns_garbage_does_not_crash():
    client = MagicMock()
    client.search.return_value = "not a dict"  # malformed
    factory = _factory_for(client)
    res = verify_facility_web_presence(
        "Apollo Hospitals", "Mumbai", "Maharashtra",
        settings=_settings(), cache=_fresh_cache(), client_factory=factory,
    )
    # No exception raised; treated as no results.
    assert isinstance(res, WebVerificationResult)
    assert res.verification_status == VERIFICATION_UNVERIFIED


def test_error_results_are_not_cached():
    """A failed call must not poison the cache."""
    cache = _fresh_cache()
    s = _settings()
    bad_client = MagicMock()
    bad_client.search.side_effect = RuntimeError("transient")
    bad_factory = _factory_for(bad_client)

    err_res = verify_facility_web_presence(
        "Apollo Hospitals", "Mumbai", "Maharashtra",
        settings=s, cache=cache, client_factory=bad_factory,
    )
    assert err_res.verification_status == VERIFICATION_ERROR
    assert cache.size() == 0

    good_client = _make_client(_strong_search_response())
    good_factory = _factory_for(good_client)
    ok_res = verify_facility_web_presence(
        "Apollo Hospitals", "Mumbai", "Maharashtra",
        settings=s, cache=cache, client_factory=good_factory,
    )
    assert ok_res.verification_status == VERIFICATION_VERIFIED
    assert cache.size() == 1


# ---------------------------------------------------------------------------
# 6. verify_top_recommendations
# ---------------------------------------------------------------------------

def _recs():
    return [
        SimpleNamespace(facility_id="F001", name="Apollo Hospitals"),
        SimpleNamespace(facility_id="F002", name="Fortis Hospital"),
        SimpleNamespace(facility_id="F003", name="Manipal Hospital"),
        SimpleNamespace(facility_id="F004", name="KIMS Hospital"),
        SimpleNamespace(facility_id="F005", name="AIIMS Delhi"),
    ]


def test_verify_top_recommendations_respects_max_to_verify():
    client = _make_client(_strong_search_response())
    factory = _factory_for(client)
    results = verify_top_recommendations(
        _recs(), max_to_verify=2, depth=DEPTH_BASIC,
        city="Mumbai", state="Maharashtra",
        settings=_settings(), cache=_fresh_cache(), client_factory=factory,
    )
    assert len(results) == 2
    assert client.search.call_count == 2
    assert results[0].facility_id == "F001"
    assert results[1].facility_id == "F002"


def test_verify_top_recommendations_respects_depth():
    client = _make_client(_strong_search_response())
    factory = _factory_for(client)
    verify_top_recommendations(
        _recs(), max_to_verify=2, depth=DEPTH_ADVANCED,
        city="Mumbai", state="Maharashtra",
        requested_capabilities=["ICU"],
        settings=_settings(), cache=_fresh_cache(), client_factory=factory,
    )
    # Each rec runs 2 advanced calls → 2 × 2 = 4 calls, all advanced.
    assert client.search.call_count == 4
    for call in client.search.call_args_list:
        assert call.kwargs["search_depth"] == "advanced"


def test_verify_top_recommendations_works_with_dicts():
    client = _make_client(_strong_search_response())
    factory = _factory_for(client)
    rec_dicts = [
        {"facility_id": "F001", "name": "Apollo Hospitals", "city": "Mumbai", "state": "Maharashtra"},
        {"facility_id": "F002", "name": "Fortis", "city": "Mumbai", "state": "Maharashtra"},
    ]
    results = verify_top_recommendations(
        rec_dicts, max_to_verify=5,
        settings=_settings(), cache=_fresh_cache(), client_factory=factory,
    )
    assert len(results) == 2
    assert results[0].facility_id == "F001"
    assert results[1].facility_id == "F002"


def test_verify_top_recommendations_empty_input_returns_empty():
    res = verify_top_recommendations(
        [], settings=_settings(), cache=_fresh_cache(),
    )
    assert res == []


def test_verify_top_recommendations_zero_limit_returns_empty():
    factory = MagicMock()
    res = verify_top_recommendations(
        _recs(), max_to_verify=0,
        settings=_settings(), cache=_fresh_cache(), client_factory=factory,
    )
    assert res == []
    factory.assert_not_called()


def test_verify_top_recommendations_disabled_returns_skipped_for_each():
    factory = MagicMock()
    s = _settings(enabled=False)
    results = verify_top_recommendations(
        _recs(), max_to_verify=2,
        settings=s, cache=_fresh_cache(), client_factory=factory,
    )
    assert len(results) == 2
    for r in results:
        assert r.verification_status == VERIFICATION_SKIPPED
    factory.assert_not_called()


def test_verify_top_recommendations_per_item_overrides():
    """Per-item ``city``/``state`` on a rec override the function defaults."""
    captured_queries: list[str] = []

    def fake_search(*, query, search_depth, max_results):
        captured_queries.append(query)
        return _strong_search_response()

    client = MagicMock()
    client.search.side_effect = fake_search
    factory = _factory_for(client)

    recs = [
        SimpleNamespace(facility_id="F001", name="Apollo Hospitals",
                        city="Mumbai", state="Maharashtra"),
        SimpleNamespace(facility_id="F002", name="Fortis Hospital",
                        city="Bangalore", state="Karnataka"),
    ]
    verify_top_recommendations(
        recs, max_to_verify=2,
        settings=_settings(), cache=_fresh_cache(), client_factory=factory,
    )
    assert "Mumbai" in captured_queries[0]
    assert "Bangalore" in captured_queries[1]


# ---------------------------------------------------------------------------
# 7. Schema invariants
# ---------------------------------------------------------------------------

def test_web_verification_result_default_values_safe():
    r = WebVerificationResult(facility_id="F100")
    assert r.web_checked is False
    assert r.web_available is False
    assert r.matched_name == ""
    assert r.matched_location == ""
    assert r.matched_capability == []
    assert r.top_url == ""
    assert r.top_snippet == ""
    assert r.verification_score == 0.0
    assert r.verification_status == "skipped"
    assert r.verification_notes == []
    assert r.error_message is None
    assert r.credits_estimated is None


def test_returned_result_has_all_new_fields_populated():
    client = _make_client(_strong_search_response())
    factory = _factory_for(client)
    res = verify_facility_web_presence(
        "Apollo Hospitals", "Mumbai", "Maharashtra",
        requested_capabilities=["ICU", "dialysis"],
        depth=DEPTH_ADVANCED,
        settings=_settings(), cache=_fresh_cache(), client_factory=factory,
    )
    for attr in (
        "web_checked", "web_available", "matched_name", "matched_location",
        "matched_capability", "top_url", "top_snippet", "verification_score",
        "verification_status", "verification_notes", "credits_estimated",
    ):
        assert hasattr(res, attr)


def test_verification_status_is_one_of_allowed_values():
    client = _make_client(_strong_search_response())
    factory = _factory_for(client)
    res = verify_facility_web_presence(
        "Apollo Hospitals", "Mumbai", "Maharashtra",
        settings=_settings(), cache=_fresh_cache(), client_factory=factory,
    )
    assert res.verification_status in {
        VERIFICATION_VERIFIED, VERIFICATION_PARTIAL,
        VERIFICATION_UNVERIFIED, VERIFICATION_SKIPPED, VERIFICATION_ERROR,
    }


# ---------------------------------------------------------------------------
# 8. Backward-compat shim
# ---------------------------------------------------------------------------

def test_verify_facility_legacy_shim_returns_skipped_when_no_key():
    res = verify_facility("Apollo Hospitals Mumbai", api_key="")
    assert isinstance(res, WebVerificationResult)
    assert res.verification_status == VERIFICATION_SKIPPED
