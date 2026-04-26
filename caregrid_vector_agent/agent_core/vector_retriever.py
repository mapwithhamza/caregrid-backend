"""
agent_core.vector_retriever — Optional Databricks Mosaic AI Vector Search client.

Design contract
---------------
This module is **always optional**. The agent must keep working when:

  * ``VECTOR_SEARCH_ENABLED=false``,
  * the Databricks workspace credentials are missing,
  * the endpoint or index has not been provisioned, or
  * any underlying SDK call raises any exception.

In every one of those cases :meth:`VectorRetriever.search` returns a
:class:`VectorSearchResponse` with ``available=False`` and a stable
``reason`` string — it never raises. The orchestrator inspects
``available`` and falls back to :mod:`agent_core.local_retriever`.

SDK choice (Stage 17)
---------------------
We use the **databricks-vectorsearch** package (``VectorSearchClient``)
rather than the lower-level ``databricks-sdk`` query API. This is the
SDK the main team validated against the live workspace, and it's the
one that accepts ``filters={"state": "Bihar"}`` as a native Python dict.
``filters_json`` is **not** used here — main-team smoke testing showed
the notebook SDK version did not accept it.

Reranker is **disabled** in the workspace (and unsupported here).

The SDK is imported lazily inside :meth:`_get_client` so importing this
module never requires the Databricks package to be installed and the
unit tests do not need the SDK to be reachable.
"""

from __future__ import annotations

from typing import Any, Iterable, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Columns we ask Databricks to return on every query. The list is the
# Stage-17 contract from the main team — note that ``score`` is NOT in
# this list because Databricks adds it automatically to every response
# manifest. Asking for it explicitly causes a column-not-found error.
DEFAULT_RETURN_COLUMNS: list[str] = [
    "facility_id",
    "name",
    "state",
    "city",
    "facility_type",
    "trust_score",
    "trust_category",
    "recommendation_readiness",
]

# Stable identifier we stamp onto every result so downstream code can
# tell vector hits apart from local-fallback hits.
SOURCE_DATABRICKS = "databricks_vector_search"

# Reason codes returned in :attr:`VectorSearchResponse.reason`. These
# are stable strings — safe to assert against in tests and to log to
# the audit trail.
REASON_DISABLED              = "vector_search_disabled"
REASON_MISSING_HOST          = "missing_databricks_host"
REASON_MISSING_TOKEN         = "missing_databricks_token"
REASON_MISSING_ENDPOINT      = "missing_vector_search_endpoint"
REASON_MISSING_INDEX         = "missing_vector_search_index"
REASON_SDK_UNAVAILABLE       = "databricks_sdk_unavailable"
REASON_QUERY_FAILED          = "query_failed"
REASON_OK                    = "ok"
REASON_OK_WITHOUT_FILTER     = "ok_without_filter"


# ---------------------------------------------------------------------------
# Result schemas
# ---------------------------------------------------------------------------

class VectorSearchResult(BaseModel):
    """A single semantic-search hit returned by the vector index."""
    facility_id: str
    similarity_score: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)
    source: str = SOURCE_DATABRICKS


class VectorSearchResponse(BaseModel):
    """
    Wrapper returned by :meth:`VectorRetriever.search`.

    Callers should branch on ``available``. When ``False``, ``results``
    is an empty list and ``reason`` is one of the ``REASON_*``
    constants above (or a ``query_failed: …`` string).

    ``filter_applied`` is True when the supplied ``filters`` dict was
    accepted by the SDK; False when the SDK rejected the filter (in
    which case the retriever transparently re-issued the query without
    the filter and the caller is responsible for any local
    post-filtering).

    ``endpoint`` and ``index`` echo the configuration that was used —
    they're safe to print and useful when debugging multi-environment
    setups.
    """
    available: bool
    results: list[VectorSearchResult] = Field(default_factory=list)
    reason: str = ""
    query: str = ""
    source: str = SOURCE_DATABRICKS
    filter_applied: bool = False
    endpoint: str = ""
    index: str = ""


# ---------------------------------------------------------------------------
# VectorRetriever
# ---------------------------------------------------------------------------

class VectorRetriever:
    """
    Optional Databricks Mosaic AI Vector Search retriever.

    The constructor takes any object that exposes the following
    attributes — the production :class:`config.settings.Settings`
    instance satisfies this, and tests pass a
    :class:`types.SimpleNamespace` for full isolation:

        vector_search_enabled  : bool
        databricks_host        : str
        databricks_token       : str
        vector_search_endpoint : str
        vector_search_index    : str
    """

    def __init__(self, settings: Any) -> None:
        self.settings = settings
        self._client: Any = None  # lazily created VectorSearchClient
        self._index: Any = None   # lazily resolved index handle

    # ------------------------------------------------------------------
    # Availability
    # ------------------------------------------------------------------

    def _unavailable_reason(self) -> Optional[str]:
        """Return a stable reason code if the retriever cannot be used, else None."""
        if not getattr(self.settings, "vector_search_enabled", False):
            return REASON_DISABLED
        if not getattr(self.settings, "databricks_host", ""):
            return REASON_MISSING_HOST
        if not getattr(self.settings, "databricks_token", ""):
            return REASON_MISSING_TOKEN
        if not getattr(self.settings, "vector_search_endpoint", ""):
            return REASON_MISSING_ENDPOINT
        if not getattr(self.settings, "vector_search_index", ""):
            return REASON_MISSING_INDEX
        return None

    def is_available(self) -> bool:
        """Cheap, side-effect-free check — does not contact Databricks."""
        return self._unavailable_reason() is None

    # ------------------------------------------------------------------
    # Client + index (lazy)
    # ------------------------------------------------------------------

    def _get_client(self) -> Any:
        """
        Build (or return cached) Databricks ``VectorSearchClient``.

        Raises :class:`ImportError` if the ``databricks-vectorsearch``
        package is not installed; :meth:`search` catches that and
        converts it to a graceful unavailable response.
        """
        if self._client is not None:
            return self._client
        from databricks.vector_search.client import VectorSearchClient  # lazy import
        self._client = VectorSearchClient(
            workspace_url=self.settings.databricks_host,
            personal_access_token=self.settings.databricks_token,
            disable_notice=True,
        )
        return self._client

    def _get_index(self) -> Any:
        """Resolve the configured index handle (cached)."""
        if self._index is not None:
            return self._index
        client = self._get_client()
        self._index = client.get_index(
            endpoint_name=self.settings.vector_search_endpoint,
            index_name=self.settings.vector_search_index,
        )
        return self._index

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(
        self,
        query: str,
        filters: dict | None = None,
        num_results: int = 20,
    ) -> VectorSearchResponse:
        """
        Run a semantic search against the configured Databricks index.

        Never raises. On any failure returns
        :class:`VectorSearchResponse` with ``available=False`` and a
        stable ``reason``.

        Filter handling
        ---------------
        ``filters`` (when supplied) is passed straight through to
        ``index.similarity_search(filters=...)`` as a Python dict — this
        is the call shape the main team confirmed works against our
        live workspace. If the installed SDK version raises
        :class:`TypeError` (e.g. it's an older build that doesn't
        accept the kwarg) the retriever transparently retries the same
        query *without* filters. In that case the response carries
        ``filter_applied=False`` and ``reason="ok_without_filter"`` so
        the caller can apply its own post-filtering and surface a
        warning. We never silently change the query text.

        Args:
            query: Natural-language query text.
            filters: Optional dict of server-side filters
                (e.g. ``{"state": "Bihar"}``).
            num_results: Top-k to ask the index for. Defaults to 20.

        Returns:
            A :class:`VectorSearchResponse` — see class docstring.
        """
        endpoint = str(getattr(self.settings, "vector_search_endpoint", "") or "")
        index    = str(getattr(self.settings, "vector_search_index",    "") or "")

        # Guard 1 — config check
        reason = self._unavailable_reason()
        if reason is not None:
            return VectorSearchResponse(
                available=False,
                reason=reason,
                query=query,
                endpoint=endpoint,
                index=index,
            )

        # Guard 2 — SDK import + index handle
        try:
            idx = self._get_index()
        except ImportError:
            return VectorSearchResponse(
                available=False,
                reason=REASON_SDK_UNAVAILABLE,
                query=query,
                endpoint=endpoint,
                index=index,
            )
        except Exception as exc:  # noqa: BLE001 — never crash the agent
            return VectorSearchResponse(
                available=False,
                reason=f"{REASON_QUERY_FAILED}: {self._short_error(exc)}",
                query=query,
                endpoint=endpoint,
                index=index,
            )

        # Guard 3 — the actual query (with filter retry on TypeError)
        return self._do_query(
            idx, query, filters, num_results, endpoint=endpoint, index=index,
        )

    def _do_query(
        self,
        idx: Any,
        query: str,
        filters: dict | None,
        num_results: int,
        *,
        endpoint: str,
        index: str,
    ) -> VectorSearchResponse:
        kwargs: dict[str, Any] = {
            "query_text": query,
            "columns": list(DEFAULT_RETURN_COLUMNS),
            "num_results": int(num_results),
        }
        # Note: we deliberately do NOT pass ``query_type``/``rerank``
        # kwargs here — reranker is disabled in the workspace.

        try:
            if filters:
                try:
                    raw = idx.similarity_search(filters=filters, **kwargs)
                    return VectorSearchResponse(
                        available=True,
                        results=self._parse_response(raw),
                        reason=REASON_OK,
                        query=query,
                        filter_applied=True,
                        endpoint=endpoint,
                        index=index,
                    )
                except TypeError:
                    # SDK does not understand the ``filters`` kwarg in
                    # this build. Fall through to the unfiltered path.
                    pass
                except Exception as exc:  # noqa: BLE001
                    # The filter itself was rejected (e.g. wrong shape
                    # for the index). Retry without filters so the
                    # caller still gets *some* results.
                    msg = self._short_error(exc)
                    if "filter" in msg.lower() or "argument" in msg.lower():
                        # Heuristic: looks filter-related → retry without
                        pass
                    else:
                        # Genuine query failure — bail out.
                        return VectorSearchResponse(
                            available=False,
                            reason=f"{REASON_QUERY_FAILED}: {msg}",
                            query=query,
                            endpoint=endpoint,
                            index=index,
                        )

                # Retry without filters, mark filter_applied=False
                raw = idx.similarity_search(**kwargs)
                return VectorSearchResponse(
                    available=True,
                    results=self._parse_response(raw),
                    reason=REASON_OK_WITHOUT_FILTER,
                    query=query,
                    filter_applied=False,
                    endpoint=endpoint,
                    index=index,
                )

            # No filter requested → straight call.
            raw = idx.similarity_search(**kwargs)
            return VectorSearchResponse(
                available=True,
                results=self._parse_response(raw),
                reason=REASON_OK,
                query=query,
                filter_applied=False,
                endpoint=endpoint,
                index=index,
            )
        except Exception as exc:  # noqa: BLE001 — never crash the agent
            return VectorSearchResponse(
                available=False,
                reason=f"{REASON_QUERY_FAILED}: {self._short_error(exc)}",
                query=query,
                endpoint=endpoint,
                index=index,
            )

    # ------------------------------------------------------------------
    # Response parsing
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_response(raw: Any) -> list[VectorSearchResult]:
        """
        Parse a Databricks Vector Search response.

        Handles both shapes returned by the supported SDKs:

        * ``databricks-vectorsearch`` (Stage 17 SDK) — the response is
          a plain ``dict`` with ``manifest.columns`` (a list of dicts
          with ``"name"`` keys) and ``result.data_array``.

        * ``databricks-sdk`` Pydantic-style objects — used by older
          tests; ``raw.manifest.columns`` (list of objects with
          ``.name`` attributes) and ``raw.result.data_array``.

        Databricks always appends a ``score`` column to every response
        manifest — we map it onto :attr:`VectorSearchResult.similarity_score`.
        Every other column (``facility_id``, ``name``, ``state``,
        ``city``, ``facility_type``, ``trust_score``, ``trust_category``,
        ``recommendation_readiness``) lands in ``metadata`` keyed by
        column name.
        """
        manifest, result = _extract_manifest_and_result(raw)
        if manifest is None or result is None:
            return []

        column_names = _extract_column_names(manifest)
        if not column_names:
            return []

        data_array = _extract_data_array(result)
        if not data_array:
            return []

        # Find the score column's index. Databricks always names it
        # ``score`` but we accept ``__db_score__`` as a defensive
        # fallback in case the SDK switches to its internal name.
        score_idx: Optional[int] = None
        for i, n in enumerate(column_names):
            if n in ("score", "__db_score__"):
                score_idx = i
                break

        out: list[VectorSearchResult] = []
        for row in data_array:
            if not isinstance(row, (list, tuple)):
                continue
            if len(row) != len(column_names):
                continue

            # Build metadata from every named column EXCEPT the score column.
            metadata: dict[str, Any] = {}
            for i, name in enumerate(column_names):
                if i == score_idx:
                    continue
                if not name:
                    continue
                metadata[name] = row[i]

            facility_id = str(metadata.get("facility_id", "") or "")

            similarity = 0.0
            if score_idx is not None:
                score_val = row[score_idx]
                try:
                    similarity = float(score_val) if score_val is not None else 0.0
                except (TypeError, ValueError):
                    similarity = 0.0

            out.append(VectorSearchResult(
                facility_id=facility_id,
                similarity_score=similarity,
                metadata=metadata,
                source=SOURCE_DATABRICKS,
            ))
        return out

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _short_error(exc: BaseException, max_len: int = 200) -> str:
        """Render an exception as a short, single-line string for the reason field."""
        msg = f"{type(exc).__name__}: {exc}".replace("\n", " ").replace("\r", " ").strip()
        return msg if len(msg) <= max_len else msg[: max_len - 3] + "..."


# ---------------------------------------------------------------------------
# Response-shape helpers (module level so tests can use them)
# ---------------------------------------------------------------------------

def _extract_manifest_and_result(raw: Any) -> tuple[Any, Any]:
    """Return ``(manifest, result)`` from either dict or attribute shape."""
    if raw is None:
        return None, None
    if isinstance(raw, dict):
        return raw.get("manifest"), raw.get("result")
    return getattr(raw, "manifest", None), getattr(raw, "result", None)


def _extract_column_names(manifest: Any) -> list[str]:
    """Pull a list of column-name strings from either dict or attribute manifest."""
    if manifest is None:
        return []
    if isinstance(manifest, dict):
        cols: Iterable[Any] = manifest.get("columns") or []
    else:
        cols = getattr(manifest, "columns", []) or []
    out: list[str] = []
    for c in cols:
        if isinstance(c, dict):
            out.append(str(c.get("name") or ""))
        else:
            out.append(str(getattr(c, "name", "") or ""))
    return out


def _extract_data_array(result: Any) -> list[Any]:
    """Pull the row list from either dict or attribute result."""
    if result is None:
        return []
    if isinstance(result, dict):
        return list(result.get("data_array") or [])
    return list(getattr(result, "data_array", None) or [])
