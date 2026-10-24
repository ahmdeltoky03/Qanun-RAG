"""The RAG pipeline: guardrails -> retrieve -> generate -> verify citations."""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

from qanun.arabic import drop_foreign_runs, has_arabic, strip_foreign_scripts
from qanun.config import Settings
from qanun.drift import DriftMonitor
from qanun.guardrails import GuardrailViolation, check_input, check_output
from qanun.llm import LLM, NOT_FOUND_AR, NOT_FOUND_EN, build_messages
from qanun.observability import CACHE, DRIFT, GUARD, Tracer
from qanun.retrieval import Retrieved, Retriever

log = logging.getLogger(__name__)


@dataclass
class AskResult:
    answer: str
    sources: list[str]
    source_details: list[dict] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)
    out_of_scope: bool = False
    blocked: bool = False
    trace_id: str = ""
    latency_ms: float = 0.0
    contexts: list[str] = field(default_factory=list)  # kept for evaluation, not returned by the API


def _detail(it: Retrieved) -> dict:
    return {
        "article_number": it.article_number,
        "citation": it.citation,
        "score": round(it.score, 4),
        "is_repealed": it.is_repealed,
        "chapter": it.chapter,
        "section": it.section,
        "text_ar": it.text_ar,
        "text_en": it.text_en,
    }


def _label(n: int, ar: bool) -> str:
    return f"المادة {n}" if ar else f"Article {n}"


def _context_block(it: Retrieved, ar: bool) -> str:
    """Exactly what the model was shown for this article (header + repeal flag + text).

    Used as the evaluation context so faithfulness is measured against the grounding the
    model actually saw — a repealed article with empty text still grounds "ملغاة / repealed".
    """
    head = _label(it.article_number, ar)
    flag = " (ملغاة)" if (ar and it.is_repealed) else " (repealed)" if it.is_repealed else ""
    body = f"{it.text_ar}\n{it.text_en}".strip()
    return f"[{head}]{flag}\n{body}".strip()


_CACHE_FIELDS = ("answer", "sources", "source_details", "flags", "out_of_scope", "contexts")


class _AnswerCache:
    """Bounded FIFO + TTL memo of finished answers, keyed by the normalized question.

    Lives on the pipeline instance, and the only ways settings or the index can change
    (edit .env, re-ingest) require an API restart — which drops the cache — so an entry can
    never outlive the retrieval/generation config that produced it.
    """

    def __init__(self, max_items: int, ttl_s: float):
        self._max, self._ttl = max_items, ttl_s
        self._d: dict[str, tuple[float, dict]] = {}

    def get(self, key: str) -> dict | None:
        hit = self._d.get(key)
        if hit is None:
            return None
        ts, val = hit
        if self._ttl and time.perf_counter() - ts > self._ttl:
            self._d.pop(key, None)
            return None
        return val

    def put(self, key: str, val: dict) -> None:
        if len(self._d) >= self._max:
            self._d.pop(next(iter(self._d)))
        self._d[key] = (time.perf_counter(), val)


class RagPipeline:
    def __init__(self, s: Settings, retriever: Retriever, llm: LLM, tracer: Tracer | None = None):
        self.s, self.retriever, self.llm = s, retriever, llm
        self.tracer = tracer or Tracer(s)
        self.drift = DriftMonitor(s.drift_baseline_path, s.drift_window, retriever.embedder.name)
        self._cache = _AnswerCache(s.answer_cache_max, s.answer_cache_ttl_s) if s.answer_cache else None

    # -- shared front half ---------------------------------------------------
    def _guard(self, question: str):
        """Start the trace and run the (cheap) input guardrails. Returns (trace, chk, blocked)."""
        trace = self.tracer.start("ask", question=question[:300])
        try:
            chk = check_input(question, self.s.max_question_chars, self.s.pii_mode)
        except GuardrailViolation as e:
            GUARD.labels(e.code).inc()
            ar = has_arabic(question)
            msg = "لا أستطيع معالجة هذا الطلب: " if ar else "I can't process this request: "
            return (
                trace,
                None,
                AskResult(msg + e.localized(ar), [], flags=[f"blocked:{e.code}"], blocked=True, trace_id=trace.id),
            )
        for f in chk.flags:
            GUARD.labels(f).inc()
        return trace, chk, None

    async def _retrieve(self, trace, chk):
        with trace.span("retrieve", question=chk.question[:200]):
            res = await self.retriever.search(chk.question)
        if res.query_vector is not None:
            d = self.drift.observe(res.query_vector)
            if d is not None:
                DRIFT.set(d)
        return res, list(chk.flags)

    # -- answer cache ---------------------------------------------------------
    def _cache_get(self, key: str) -> dict | None:
        if self._cache is None:
            return None
        val = self._cache.get(key)
        CACHE.labels("hit" if val is not None else "miss").inc()
        return val

    def _cache_put(self, key: str, r: AskResult) -> None:
        if self._cache is not None and not r.blocked:
            self._cache.put(key, {k: getattr(r, k) for k in _CACHE_FIELDS})

    def _cache_hit(self, trace, cached: dict, t0: float) -> AskResult:
        out = AskResult(
            trace_id=trace.id,
            latency_ms=round((time.perf_counter() - t0) * 1000, 1),
            **{**cached, "flags": cached["flags"] + ["cache:hit"]},
        )
        trace.finish({"answer": out.answer, "sources": out.sources, "cache": "hit"})
        return out

    def _finish(self, trace, question, res, flags, answer, t0) -> AskResult:
        ar = has_arabic(question)
        allowed = {i.article_number for i in res.items}
        cleaned = strip_foreign_scripts(answer, ar)
        if cleaned != answer:
            flags = flags + ["sanitized:foreign_script"]
        answer, out_flags = check_output(cleaned, allowed)
        flags = flags + out_flags
        sources = (
            [_label(i.article_number, ar) for i in res.items] if answer not in (NOT_FOUND_AR, NOT_FOUND_EN) else []
        )
        out = AskResult(
            answer=answer or (NOT_FOUND_AR if ar else NOT_FOUND_EN),
            sources=sources,
            source_details=[_detail(i) for i in res.items] if sources else [],
            flags=flags,
            trace_id=trace.id,
            latency_ms=round((time.perf_counter() - t0) * 1000, 1),
            contexts=[_context_block(i, ar) for i in res.items],
        )
        trace.finish({"answer": out.answer, "sources": out.sources, "flags": flags})
        return out

    # -- public API ------------------------------------------------------------
    async def ask(self, question: str) -> AskResult:
        t0 = time.perf_counter()
        trace, chk, blocked = self._guard(question)
        if blocked:
            return blocked
        cached = self._cache_get(chk.question)
        if cached is not None:
            return self._cache_hit(trace, cached, t0)
        res, flags = await self._retrieve(trace, chk)
        ar = has_arabic(chk.question)
        if res.out_of_scope or not res.items:
            out = AskResult(
                NOT_FOUND_AR if ar else NOT_FOUND_EN,
                [],
                flags=flags + ["out_of_scope"],
                out_of_scope=True,
                trace_id=trace.id,
                latency_ms=round((time.perf_counter() - t0) * 1000, 1),
            )
            trace.finish({"answer": out.answer, "out_of_scope": True})
            self._cache_put(chk.question, out)
            return out
        failed = False
        try:
            with trace.span("generate", model=self.llm.name):
                answer = await self.llm.complete(build_messages(chk.question, res.items))
        except Exception as e:  # upstream LLM/network error (e.g. 429, timeout)
            failed, answer = True, ""
            log.warning("ask generation failed: %s", e)
        out = self._finish(trace, chk.question, res, flags, answer, t0)
        if failed:
            out.flags = [*out.flags, "error:upstream"]  # never cache a failed answer
        else:
            self._cache_put(chk.question, out)
        return out

    async def ask_stream(self, question: str) -> AsyncIterator[dict]:
        """Yields {"event": "meta"|"token"|"done", ...} dicts (the API turns them into SSE)."""
        t0 = time.perf_counter()
        trace, chk, blocked = self._guard(question)
        if blocked:
            yield {"event": "done", "data": blocked}
            return
        cached = self._cache_get(chk.question)
        if cached is not None:
            out = self._cache_hit(trace, cached, t0)
            yield {"event": "meta", "sources": out.sources, "trace_id": trace.id}
            yield {"event": "token", "text": out.answer}
            yield {"event": "done", "data": out}
            return
        res, flags = await self._retrieve(trace, chk)
        ar = has_arabic(chk.question)
        if res.out_of_scope or not res.items:
            out = AskResult(
                NOT_FOUND_AR if ar else NOT_FOUND_EN,
                [],
                flags=flags + ["out_of_scope"],
                out_of_scope=True,
                trace_id=trace.id,
            )
            self._cache_put(chk.question, out)
            yield {"event": "done", "data": out}
            return
        yield {"event": "meta", "sources": [_label(i.article_number, ar) for i in res.items], "trace_id": trace.id}
        parts: list[str] = []
        failed = False
        try:
            with trace.span("generate", model=self.llm.name):
                async for tok in self.llm.stream(build_messages(chk.question, res.items)):
                    tok = drop_foreign_runs(tok, ar)  # never stream leaked foreign scripts to the UI
                    if not tok:
                        continue
                    parts.append(tok)
                    yield {"event": "token", "text": tok}
        except Exception as e:  # upstream LLM/network error mid-stream (e.g. 429, timeout)
            failed = True
            log.warning("ask_stream generation failed mid-stream: %s", e)
        # Always emit a terminal frame: a stream that just stops leaves the UI hanging
        # (or, with the old client, wiping the partial answer). On failure surface a flag
        # and skip the cache so a transient upstream error is never memoized.
        out = self._finish(trace, chk.question, res, flags, "".join(parts), t0)
        if failed:
            out.flags = [*out.flags, "error:upstream"]
        else:
            self._cache_put(chk.question, out)
        yield {"event": "done", "data": out}
