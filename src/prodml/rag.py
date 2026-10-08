"""The RAG pipeline: guardrails -> retrieve -> generate -> verify citations."""

from __future__ import annotations

import time
from collections.abc import Iterator
from dataclasses import dataclass, field

from prodml.arabic import has_arabic
from prodml.config import Settings
from prodml.drift import DriftMonitor
from prodml.guardrails import GuardrailViolation, check_input, check_output
from prodml.llm import LLM, NOT_FOUND_AR, NOT_FOUND_EN, build_messages
from prodml.observability import DRIFT, GUARD, Tracer
from prodml.retrieval import Retrieved, Retriever


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


class RagPipeline:
    def __init__(self, s: Settings, retriever: Retriever, llm: LLM, tracer: Tracer | None = None):
        self.s, self.retriever, self.llm = s, retriever, llm
        self.tracer = tracer or Tracer(s)
        self.drift = DriftMonitor(s.drift_baseline_path, s.drift_window, retriever.embedder.name)

    # -- shared front half ---------------------------------------------------
    def _prepare(self, question: str):
        trace = self.tracer.start("ask", question=question[:300])
        flags: list[str] = []
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
        flags += chk.flags
        for f in chk.flags:
            GUARD.labels(f).inc()
        with trace.span("retrieve", question=chk.question[:200]):
            res = self.retriever.search(chk.question)
        if res.query_vector is not None:
            d = self.drift.observe(res.query_vector)
            if d is not None:
                DRIFT.set(d)
        return trace, (chk.question, res, flags), None

    def _finish(self, trace, question, res, flags, answer, t0) -> AskResult:
        ar = has_arabic(question)
        allowed = {i.article_number for i in res.items}
        answer, out_flags = check_output(answer, allowed)
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
            contexts=[f"{i.text_ar}\n{i.text_en}".strip() for i in res.items],
        )
        trace.finish({"answer": out.answer, "sources": out.sources, "flags": flags})
        return out

    # -- public API ------------------------------------------------------------
    def ask(self, question: str) -> AskResult:
        t0 = time.perf_counter()
        trace, ctx, blocked = self._prepare(question)
        if blocked:
            return blocked
        q, res, flags = ctx
        ar = has_arabic(q)
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
            return out
        with trace.span("generate", model=self.llm.name):
            answer = self.llm.complete(build_messages(q, res.items))
        return self._finish(trace, q, res, flags, answer, t0)

    def ask_stream(self, question: str) -> Iterator[dict]:
        """Yields {"event": "meta"|"token"|"done", ...} dicts (the API turns them into SSE)."""
        t0 = time.perf_counter()
        trace, ctx, blocked = self._prepare(question)
        if blocked:
            yield {"event": "done", "data": blocked}
            return
        q, res, flags = ctx
        ar = has_arabic(q)
        if res.out_of_scope or not res.items:
            out = AskResult(
                NOT_FOUND_AR if ar else NOT_FOUND_EN,
                [],
                flags=flags + ["out_of_scope"],
                out_of_scope=True,
                trace_id=trace.id,
            )
            yield {"event": "done", "data": out}
            return
        yield {"event": "meta", "sources": [_label(i.article_number, ar) for i in res.items], "trace_id": trace.id}
        parts: list[str] = []
        with trace.span("generate", model=self.llm.name):
            for tok in self.llm.stream(build_messages(q, res.items)):
                parts.append(tok)
                yield {"event": "token", "text": tok}
        yield {"event": "done", "data": self._finish(trace, q, res, flags, "".join(parts), t0)}
