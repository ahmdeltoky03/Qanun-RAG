"""Langfuse integration, tested against a fake SDK (no server needed).

This proves our *call pattern* and, more importantly, that tracing can never break serving.
It does not prove compatibility with a specific langfuse release: run `docker compose --profile tracing up`
and open http://localhost:3000 for that.
"""

from __future__ import annotations

import sys
import types

import pytest

from qanun.config import Settings
from qanun.observability import Tracer
from qanun.rag import RagPipeline


class FakeSpan:
    def __init__(self, log, name):
        self.log, self.name = log, name

    def end(self):
        self.log.append(("span_end", self.name))


class FakeTrace:
    def __init__(self, log, name, input):
        self.id, self.log = f"trace-{len(log)}", log
        log.append(("trace", name))

    def span(self, name, input=None):
        self.log.append(("span", name))
        return FakeSpan(self.log, name)

    def update(self, output=None):
        self.log.append(("update", sorted(output)))

    def score(self, name, value, comment=""):
        self.log.append(("score", name, value))


class FakeLangfuse:
    log: list = []
    explode = False

    def __init__(self, **kw):
        assert kw["host"] and kw["public_key"] and kw["secret_key"]

    def trace(self, name, input=None):
        if FakeLangfuse.explode:
            raise RuntimeError("langfuse is down")
        return FakeTrace(self.log, name, input)

    def score(self, trace_id, name, value):
        self.log.append(("score_by_id", trace_id, name, value))

    def flush(self):
        self.log.append(("flush",))


@pytest.fixture
def fake_langfuse(monkeypatch):
    FakeLangfuse.log, FakeLangfuse.explode = [], False
    monkeypatch.setitem(sys.modules, "langfuse", types.SimpleNamespace(Langfuse=FakeLangfuse))
    return FakeLangfuse


def _traced(settings: Settings, pipeline: RagPipeline) -> RagPipeline:
    """Same retriever/LLM (embedded Qdrant allows one client per folder), but with Langfuse enabled."""
    s = settings.model_copy(update={"langfuse_public_key": "pk", "langfuse_secret_key": "sk"})
    return RagPipeline(s, pipeline.retriever, pipeline.llm, Tracer(s))


def test_tracer_disabled_without_keys(settings):
    assert Tracer(settings).enabled is False


async def test_ask_creates_trace_with_stage_spans(fake_langfuse, settings, pipeline):
    pipe = _traced(settings, pipeline)
    res = await pipe.ask("ماذا تقول المادة 805؟")
    kinds = [e[:2] for e in fake_langfuse.log]
    assert ("trace", "ask") in kinds and ("span", "retrieve") in kinds and ("span", "generate") in kinds
    assert ("span_end", "retrieve") in kinds and ("span_end", "generate") in kinds
    assert any(e[0] == "update" for e in fake_langfuse.log)
    assert res.trace_id.startswith("trace-")


async def test_faithfulness_score_is_linked_to_trace(fake_langfuse, settings, pipeline):
    pipe = _traced(settings, pipeline)
    res = await pipe.ask("ماذا تقول المادة 805؟")
    pipe.tracer.score(res.trace_id, "faithfulness", 0.9)
    assert ("score_by_id", res.trace_id, "faithfulness", 0.9) in fake_langfuse.log


async def test_langfuse_outage_never_breaks_answers(fake_langfuse, settings, pipeline):
    pipe = _traced(settings, pipeline)
    fake_langfuse.explode = True
    res = await pipe.ask("ماذا تقول المادة 805؟")
    assert res.sources == ["المادة 805"] and res.trace_id  # fell back to a local trace id
