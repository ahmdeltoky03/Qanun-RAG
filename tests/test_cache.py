"""Answer cache: repeat questions are served from memory, skipping retrieve + generate.

These reuse the shared session `pipeline`'s retriever (embedded Qdrant allows only one
client per folder) but wrap the LLM in a call-counter so we can prove the second identical
question never reaches retrieval or generation.
"""

from __future__ import annotations

from qanun.config import Settings
from qanun.observability import Tracer
from qanun.rag import RagPipeline


class CountingLLM:
    """Transparent wrapper that counts how many times the LLM is actually invoked."""

    name = "counting"

    def __init__(self, inner):
        self._inner = inner
        self.complete_calls = 0
        self.stream_calls = 0

    async def complete(self, messages):
        self.complete_calls += 1
        return await self._inner.complete(messages)

    async def stream(self, messages):
        self.stream_calls += 1
        async for tok in self._inner.stream(messages):
            yield tok


def _pipe(settings: Settings, pipeline: RagPipeline, cache: bool) -> tuple[RagPipeline, CountingLLM]:
    """Fresh pipeline sharing the session retriever, with a counting LLM and cache on/off."""
    s = settings.model_copy(update={"answer_cache": cache})
    llm = CountingLLM(pipeline.llm)
    return RagPipeline(s, pipeline.retriever, llm, Tracer(s)), llm


Q = "ماذا تقول المادة 805؟"


async def test_repeat_question_hits_cache_and_skips_llm(settings, pipeline):
    pipe, llm = _pipe(settings, pipeline, cache=True)

    first = await pipe.ask(Q)
    assert llm.complete_calls == 1
    assert "cache:hit" not in first.flags

    second = await pipe.ask(Q)
    assert llm.complete_calls == 1  # LLM never invoked again
    assert "cache:hit" in second.flags
    assert second.answer == first.answer
    assert second.sources == first.sources
    assert second.source_details == first.source_details


async def test_cache_hit_is_still_traced_and_faster(settings, pipeline):
    pipe, _ = _pipe(settings, pipeline, cache=True)

    first = await pipe.ask(Q)
    second = await pipe.ask(Q)

    assert second.trace_id  # a real trace is still started on a hit
    assert second.latency_ms <= first.latency_ms  # relative, avoids flaky absolute thresholds


async def test_streaming_hit_emits_meta_token_done(settings, pipeline):
    pipe, llm = _pipe(settings, pipeline, cache=True)

    # Prime the cache with a non-streaming ask so we know generation ran exactly once.
    first = await pipe.ask(Q)
    assert llm.complete_calls == 1

    events = [ev async for ev in pipe.ask_stream(Q)]
    assert [e["event"] for e in events] == ["meta", "token", "done"]
    assert llm.stream_calls == 0 and llm.complete_calls == 1  # nothing regenerated
    done = events[-1]["data"]
    assert "cache:hit" in done.flags
    assert done.answer == first.answer
    assert events[1]["text"] == first.answer  # whole cached answer streamed in one token


async def test_blocked_requests_are_not_cached(settings, pipeline):
    pipe, llm = _pipe(settings, pipeline, cache=True)
    long_q = "؟" * (settings.max_question_chars + 50)

    a = await pipe.ask(long_q)
    b = await pipe.ask(long_q)
    assert a.blocked and b.blocked
    assert "cache:hit" not in b.flags  # blocked answers are never memoized
    assert llm.complete_calls == 0


async def test_cache_disabled_regenerates_every_time(settings, pipeline):
    pipe, llm = _pipe(settings, pipeline, cache=False)

    first = await pipe.ask(Q)
    second = await pipe.ask(Q)
    assert llm.complete_calls == 2  # no memoization when the cache is off
    assert "cache:hit" not in second.flags
    assert second.answer == first.answer


async def test_out_of_scope_is_cached(settings, pipeline):
    pipe, llm = _pipe(settings, pipeline, cache=True)
    oos = "ما هو أفضل مطعم في القاهرة؟"

    first = await pipe.ask(oos)
    second = await pipe.ask(oos)
    assert first.out_of_scope
    assert "cache:hit" in second.flags
    assert second.out_of_scope
    assert llm.complete_calls == 0  # refusal short-circuits before generation both times
