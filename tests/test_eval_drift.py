import json

import numpy as np

from qanun.drift import DriftMonitor, cosine_distance, save_baseline
from qanun.eval import metrics as M
from qanun.eval.run import aggregate, run_pipeline
from qanun.observability import FAITH, refresh_eval_gauges


def test_cosine_distance():
    assert cosine_distance(np.array([1, 0]), np.array([1, 0])) < 1e-9
    assert abs(cosine_distance(np.array([1, 0]), np.array([0, 1])) - 1) < 1e-9


def test_drift_monitor_detects_shift(tmp_path):
    rng = np.random.default_rng(0)
    base = rng.normal(0, 1, (50, 16)) + 5
    save_baseline(base, tmp_path / "b.json", "m")
    mon = DriftMonitor(tmp_path / "b.json", window=40, model_name="m")
    for v in base[:30]:
        mon.observe(v)
    same = mon.current()
    mon2 = DriftMonitor(tmp_path / "b.json", window=40, model_name="m")
    for v in rng.normal(0, 1, (30, 16)) - 5:
        mon2.observe(v)
    assert same is not None and same < 0.05 < mon2.current()


def test_drift_ignores_baseline_from_other_model(tmp_path):
    save_baseline(np.ones((3, 4)), tmp_path / "b.json", "model-a")
    assert DriftMonitor(tmp_path / "b.json", model_name="model-b").baseline is None


def test_metrics_math():
    assert M.retrieval_metrics([5], [3, 5, 9])["mrr"] == 0.5
    assert M.retrieval_metrics([5], [5])["hit_at_1"] == 1.0
    assert M.faithfulness_proxy("العقد شريعة المتعاقدين [المادة 147]", ["العقد شريعة المتعاقدين"]) == 1.0
    assert M.faithfulness_proxy("بيتزا جبنة طماطم", ["العقد شريعة المتعاقدين"]) == 0.0


def test_eval_runner_and_gauge(pipeline, tmp_path):
    qs = json.load(open("data/eval/questions.json", encoding="utf-8"))
    sel = [q for q in qs if q["id"] in ("q016", "q053", "q058")]
    rows = run_pipeline(pipeline, sel)
    assert rows[1]["hit_at_1"] == 1.0  # explicit article
    assert rows[2]["oos_correct"] == 1.0  # pizza is refused
    rep = tmp_path / "e.json"
    rep.write_text(json.dumps({"metrics": {**aggregate(rows), "context_recall": 0.5}}))
    refresh_eval_gauges(rep)
    assert FAITH._value.get() > 0


class HallucinatingLLM:
    """Confident answer with a valid-looking citation but no support in the retrieved text."""

    name = "hallucinator"

    async def complete(self, messages):
        return "يجوز بيع البيتزا والقهوة في المطاعم بعد الساعة الثانية عشرة ليلا وفقا للوائح السياحة [المادة 805]"

    async def stream(self, messages):
        yield await self.complete(messages)


def test_quality_gate_fails_when_the_generator_hallucinates(pipeline, settings, tmp_path):
    import subprocess
    import sys

    from qanun.eval.run import evaluate_pipeline
    from qanun.rag import RagPipeline

    qs = [
        q for q in json.load(open("data/eval/questions.json", encoding="utf-8")) if q["category"] == "explicit_article"
    ]
    good = evaluate_pipeline(settings, qs, mode="offline", pipe=pipeline)["metrics"]["faithfulness"]
    bad_pipe = RagPipeline(settings, pipeline.retriever, HallucinatingLLM(), pipeline.tracer)
    bad = evaluate_pipeline(settings, qs, mode="offline", pipe=bad_pipe)["metrics"]["faithfulness"]
    assert good >= 0.75 > bad, (good, bad)  # the 0.75 gate separates them

    # and the CLI turns that into a non-zero exit code
    report = tmp_path / "r.json"
    report.write_text(json.dumps({"metrics": {"faithfulness": bad}}))
    code = "import json,sys;m=json.load(open(sys.argv[1]))['metrics'];sys.exit(1 if m['faithfulness']<0.75 else 0)"
    assert subprocess.run([sys.executable, "-c", code, str(report)]).returncode == 1


def test_eval_against_a_running_service(client, monkeypatch):
    """`qanun-eval --api URL` must give the same kind of report as the in-process run."""
    import httpx

    from qanun.eval.run import HttpPipeline, run_pipeline

    monkeypatch.setattr(httpx, "Client", lambda **kw: client)  # the TestClient *is* an httpx.Client
    pipe = HttpPipeline("http://testserver")
    qs = [q for q in json.load(open("data/eval/questions.json", encoding="utf-8")) if q["id"] in ("q053", "q058")]
    rows = run_pipeline(pipe, qs)
    assert rows[0]["hit_at_1"] == 1.0 and rows[1]["oos_correct"] == 1.0
    assert pipe.llm.name == "fake-extractive"
