"""Prometheus metrics + optional Langfuse tracing (no-op when Langfuse is not configured)."""

from __future__ import annotations

import json
import logging
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram

from prodml.config import Settings

log = logging.getLogger(__name__)
REGISTRY = CollectorRegistry()

REQUESTS = Counter("rag_requests_total", "Requests to /ask", ["outcome", "release"], registry=REGISTRY)
LATENCY = Histogram(
    "rag_request_seconds", "End-to-end /ask latency", buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 4, 8, 16), registry=REGISTRY
)
STAGE = Histogram("rag_stage_seconds", "Latency per pipeline stage", ["stage"], registry=REGISTRY)
GUARD = Counter("rag_guardrail_total", "Guardrail activations", ["code"], registry=REGISTRY)
DOCS = Gauge("rag_documents_indexed", "Distinct articles in the index", registry=REGISTRY)
FAITH = Gauge("rag_faithfulness", "Latest offline-eval faithfulness (0-1)", registry=REGISTRY)
CTX_RECALL = Gauge("rag_context_recall", "Latest offline-eval context recall (0-1)", registry=REGISTRY)
DRIFT = Gauge("rag_query_drift_cosine", "Cosine distance between recent query centroid and baseline", registry=REGISTRY)
EVAL_AGE = Gauge("rag_eval_report_age_seconds", "Age of the latest eval report", registry=REGISTRY)


def refresh_eval_gauges(path: Path) -> None:
    """Called on every scrape: publish the newest offline eval result as gauges."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        FAITH.set(float(data["metrics"]["faithfulness"]))
        CTX_RECALL.set(float(data["metrics"].get("context_recall", 0.0)))
        EVAL_AGE.set(max(0.0, time.time() - path.stat().st_mtime))
    except (OSError, KeyError, ValueError):
        pass


class Trace:
    """Minimal trace facade. Real Langfuse calls happen only when credentials are configured."""

    def __init__(self, lf_trace=None):
        self._t = lf_trace
        self.id = getattr(lf_trace, "id", None) or uuid.uuid4().hex

    @contextmanager
    def span(self, name: str, **input_):
        t0 = time.perf_counter()
        sp = None
        if self._t is not None:
            try:
                sp = self._t.span(name=name, input=input_ or None)
            except Exception:  # tracing must never break serving
                log.exception("langfuse span failed")
        try:
            yield
        finally:
            STAGE.labels(name).observe(time.perf_counter() - t0)
            if sp is not None:
                try:
                    sp.end()
                except Exception:
                    log.exception("langfuse span end failed")

    def finish(self, output: dict) -> None:
        if self._t is not None:
            try:
                self._t.update(output=output)
            except Exception:
                log.exception("langfuse update failed")

    def score(self, name: str, value: float, comment: str = "") -> None:
        if self._t is not None:
            try:
                self._t.score(name=name, value=value, comment=comment)
            except Exception:
                log.exception("langfuse score failed")


class Tracer:
    def __init__(self, s: Settings):
        self._lf = None
        if s.langfuse_public_key and s.langfuse_secret_key:
            try:
                from langfuse import Langfuse  # optional dependency

                self._lf = Langfuse(
                    public_key=s.langfuse_public_key, secret_key=s.langfuse_secret_key, host=s.langfuse_host
                )
                log.info("Langfuse tracing enabled (%s)", s.langfuse_host)
            except Exception:
                log.exception("Langfuse unavailable; continuing without tracing")

    @property
    def enabled(self) -> bool:
        return self._lf is not None

    def start(self, name: str, **input_) -> Trace:
        if self._lf is None:
            return Trace()
        try:
            return Trace(self._lf.trace(name=name, input=input_))
        except Exception:
            log.exception("langfuse trace failed")
            return Trace()

    def score(self, trace_id: str, name: str, value: float) -> None:
        if self._lf is not None:
            try:
                self._lf.score(trace_id=trace_id, name=name, value=value)
            except Exception:
                log.exception("langfuse score failed")

    def flush(self) -> None:
        if self._lf is not None:
            self._lf.flush()
