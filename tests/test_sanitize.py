"""Output sanitisation: foreign-script leakage is stripped, and eval contexts mirror the prompt.

Small serving models occasionally leak Chinese runs or stray Latin/Arabic words into an
answer in the other language. The pipeline must never show or memoise that leakage, and
faithfulness must be scored against exactly what the model was shown (repeal flag included).
"""

from __future__ import annotations

from qanun.arabic import drop_foreign_runs, strip_foreign_scripts
from qanun.config import Settings
from qanun.observability import Tracer
from qanun.rag import RagPipeline, _context_block
from qanun.retrieval import Retrieved


class LeakyLLM:
    """Returns a canned answer that leaks foreign scripts, the way small models do."""

    name = "leaky"

    def __init__(self, answer: str):
        self._answer = answer

    async def complete(self, messages):
        return self._answer

    async def stream(self, messages):
        for tok in self._answer.split(" "):
            yield tok + " "


def _pipe(settings: Settings, pipeline: RagPipeline, answer: str) -> RagPipeline:
    s = settings.model_copy(update={"answer_cache": False})
    return RagPipeline(s, pipeline.retriever, LeakyLLM(answer), Tracer(s))


Q_AR = "ما هي سلطات المالك على الشيء المملوك؟"


def test_strip_foreign_scripts_arabic():
    dirty = "سلطات المالك تشمل: 1.使用权和利用标的物。 2.处分标的物。 وفقا للمادة 802 occurrence."
    clean = strip_foreign_scripts(dirty, True)
    assert "使用权" not in clean and "occurrence" not in clean and "1. 2." not in clean
    assert "سلطات المالك تشمل:" in clean and "وفقا للمادة 802" in clean
    assert clean == strip_foreign_scripts(clean, True)  # idempotent


def test_strip_foreign_scripts_english():
    clean = strip_foreign_scripts("The owner may use the thing. المادة 802", False)
    assert "المادة" not in clean
    assert "The owner may use the thing." in clean


def test_drop_foreign_runs_keeps_whitespace():
    assert drop_foreign_runs("hello world", False) == "hello world"
    assert drop_foreign_runs("a 使用 b", False) == "a  b"  # chars removed, spacing untouched
    assert drop_foreign_runs("نص عربي", True) == "نص عربي"


def test_context_block_includes_header_and_repeal_flag():
    it = Retrieved(
        article_number=60, citation="c", score=0.5, is_repealed=True,
        chapter="ch", section="", text_ar="", text_en="",
    )  # fmt: skip
    assert "[المادة 60] (ملغاة)" in _context_block(it, True)
    assert "[Article 60] (repealed)" in _context_block(it, False)
    plain = Retrieved(
        article_number=802, citation="c", score=0.5, is_repealed=False,
        chapter="ch", section="", text_ar="نص", text_en="text",
    )  # fmt: skip
    assert _context_block(plain, True) == "[المادة 802]\nنص\ntext"


async def test_ask_strips_leaked_scripts_and_flags(settings, pipeline):
    probe = await _pipe(settings, pipeline, "x").ask(Q_AR)  # learn which articles retrieval allows
    n = probe.sources[0].split()[-1]
    pipe = _pipe(settings, pipeline, f"للمالك استعمال الشيء. 使用权。 [المادة {n}] occurrence")
    out = await pipe.ask(Q_AR)
    assert "使用权" not in out.answer and "occurrence" not in out.answer
    assert "للمالك استعمال الشيء." in out.answer
    assert "sanitized:foreign_script" in out.flags
    assert f"[المادة {n}]" in out.answer  # grounded citation survives


async def test_stream_never_emits_foreign_scripts(settings, pipeline):
    pipe = _pipe(settings, pipeline, "الجواب هنا. 使用权。 [المادة 802]")
    events = [e async for e in pipe.ask_stream(Q_AR)]
    streamed = "".join(e["text"] for e in events if e["event"] == "token")
    assert "使用权" not in streamed
    done = [e for e in events if e["event"] == "done"][-1]["data"]
    assert "sanitized:foreign_script" in done.flags or "使用权" not in done.answer


async def test_clean_answer_is_not_flagged(settings, pipeline):
    pipe = _pipe(settings, pipeline, "للمالك استعمال الشيء [المادة 802]")
    out = await pipe.ask(Q_AR)
    assert "sanitized:foreign_script" not in out.flags
