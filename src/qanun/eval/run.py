"""Run the evaluation set against the live pipeline and write a JSON report.

qanun-eval --questions data/eval/questions.json --out reports/latest_eval.json
qanun-eval --sample 20 --gate --min-faithfulness 0.75      # CI quality gate
qanun-eval --mode ragas                                      # needs a judge LLM (see README)
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import sys
import time
from pathlib import Path

from qanun.api.main import build_pipeline
from qanun.config import Settings, get_settings
from qanun.eval import metrics as M
from qanun.rag import RagPipeline

log = logging.getLogger(__name__)


class HttpPipeline:
    """Evaluate a *running* service (e.g. the Docker stack behind nginx, with the real LLM) through its public API."""

    class _Named:
        def __init__(self, name: str):
            self.name = name
            self.embedder = self

    def __init__(self, base_url: str):
        import httpx

        self.base, self._http = base_url.rstrip("/"), httpx.Client(timeout=180)
        h = self._http.get(f"{self.base}/health").raise_for_status().json()
        self.retriever = self._Named(h["embedding_model"])
        self.llm = self._Named(h["llm_model"])
        self.tracer = type("NoTracer", (), {"enabled": False})()

    def ask(self, question: str):
        from qanun.rag import AskResult

        d = self._http.post(f"{self.base}/ask", json={"question": question}).raise_for_status().json()
        return AskResult(
            answer=d["answer"], sources=d["sources"], source_details=d["source_details"], flags=d["flags"],
            out_of_scope=d["out_of_scope"], blocked=d["blocked"], trace_id=d["trace_id"], latency_ms=d["latency_ms"],
            contexts=[f"{x['text_ar']}\n{x['text_en']}".strip() for x in d["source_details"]],
        )  # fmt: skip


def run_pipeline(pipe: RagPipeline, questions: list[dict]) -> list[dict]:
    rows = []
    for q in questions:
        res = pipe.ask(q["question"])
        retrieved = [int(s.split()[-1]) for s in res.sources]
        row = {
            "id": q["id"], "question": q["question"], "category": q["category"], "lang": q["lang"],
            "expected_articles": q["expected_articles"], "reference": q["reference"],
            "answer": res.answer, "sources": res.sources, "contexts": res.contexts,
            "refused": M.is_refusal(res.answer) or res.out_of_scope, "latency_ms": res.latency_ms,
            "trace_id": res.trace_id,
        }  # fmt: skip
        if q["expected_articles"]:
            row.update(M.retrieval_metrics(q["expected_articles"], retrieved))
            row["citation_accuracy"] = M.citation_accuracy(res.answer, q["expected_articles"])
            row["answer_relevancy"] = M.token_f1(res.answer, q["reference"])
            row["faithfulness"] = M.faithfulness_proxy(res.answer, res.contexts)
        else:  # out-of-scope: the right behaviour is to refuse
            row["oos_correct"] = float(row["refused"])
            row["faithfulness"] = 1.0 if row["refused"] else 0.0
        rows.append(row)
    return rows


def aggregate(rows: list[dict]) -> dict[str, float]:
    inscope = [r for r in rows if r["expected_articles"]]
    oos = [r for r in rows if not r["expected_articles"]]
    out = {
        "faithfulness": M.mean([r["faithfulness"] for r in rows]),
        "answer_relevancy": M.mean([r["answer_relevancy"] for r in inscope]),
        "context_precision": M.mean([r["context_precision"] for r in inscope]),
        "context_recall": M.mean([r["context_recall"] for r in inscope]),
        "hit_at_1": M.mean([r["hit_at_1"] for r in inscope]),
        "hit_at_k": M.mean([r["hit_at_k"] for r in inscope]),
        "mrr": M.mean([r["mrr"] for r in inscope]),
        "citation_accuracy": M.mean([r["citation_accuracy"] for r in inscope]),
        "oos_accuracy": M.mean([r["oos_correct"] for r in oos]),
        "p50_latency_ms": sorted(r["latency_ms"] for r in rows)[len(rows) // 2],
    }
    return out


def ragas_scores(rows: list[dict]) -> dict[str, float]:
    """Authoritative RAGAS metrics (LLM-as-judge). Requires `pip install qanun[eval]` and a judge model."""
    import os

    from datasets import Dataset
    from langchain_openai import ChatOpenAI, OpenAIEmbeddings
    from ragas import evaluate
    from ragas.metrics import answer_relevancy, context_precision, context_recall, faithfulness

    inscope = [r for r in rows if r["expected_articles"] and not r["refused"]]
    ds = Dataset.from_dict({
        "question": [r["question"] for r in inscope], "answer": [r["answer"] for r in inscope],
        "contexts": [r["contexts"] for r in inscope], "ground_truth": [r["reference"] for r in inscope],
    })  # fmt: skip
    llm = ChatOpenAI(
        model=os.environ.get("RAGAS_JUDGE_MODEL", "gpt-4o-mini"),
        base_url=os.environ.get("RAGAS_BASE_URL"),
        temperature=0,
    )
    emb = OpenAIEmbeddings(
        model=os.environ.get("RAGAS_EMBED_MODEL", "text-embedding-3-small"), base_url=os.environ.get("RAGAS_BASE_URL")
    )
    res = evaluate(
        ds, metrics=[faithfulness, answer_relevancy, context_precision, context_recall], llm=llm, embeddings=emb
    )
    df = res.to_pandas()
    return {
        k: round(float(df[k].mean()), 4)
        for k in ("faithfulness", "answer_relevancy", "context_precision", "context_recall")
    }


def evaluate_pipeline(s: Settings, questions: list[dict], mode: str = "auto", pipe: RagPipeline | None = None) -> dict:
    pipe = pipe or build_pipeline(s)
    t0 = time.perf_counter()
    rows = run_pipeline(pipe, questions)
    metrics = aggregate(rows)
    used = "offline-proxy"
    if mode in ("auto", "ragas"):
        try:
            ragas = ragas_scores(rows)
            metrics.update({f"offline_{k}": metrics[k] for k in ragas})
            metrics.update(ragas)
            used = "ragas"
        except Exception as e:  # missing package / no judge credentials
            if mode == "ragas":
                raise
            log.warning("RAGAS unavailable (%s: %s); using offline proxy metrics", type(e).__name__, e)
    report = {
        "mode": used, "n": len(rows), "metrics": metrics, "seconds": round(time.perf_counter() - t0, 1),
        "config": {
            "embedding": pipe.retriever.embedder.name, "llm": pipe.llm.name, "chunk_size": s.chunk_size, "top_k": s.top_k,
            "rerank": s.rerank, "dense_weight": s.dense_weight,
        },
        "per_question": [{k: v for k, v in r.items() if k != "contexts"} for r in rows],
    }  # fmt: skip
    if pipe.tracer.enabled:  # link the score to its trace so a bad answer can be opened in Langfuse
        for r in rows:
            pipe.tracer.score(r["trace_id"], "faithfulness", r["faithfulness"])
        pipe.tracer.flush()
    return report


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--questions", type=Path, default=Path("data/eval/questions.json"))
    ap.add_argument("--out", type=Path, default=Path("reports/latest_eval.json"))
    ap.add_argument("--mode", choices=["auto", "ragas", "offline"], default="offline")
    ap.add_argument("--sample", type=int, default=0, help="evaluate a deterministic random sample of N questions")
    ap.add_argument("--api", help="evaluate a running service at this URL instead of loading the index in-process")
    ap.add_argument("--gate", action="store_true", help="exit 1 if faithfulness is below --min-faithfulness")
    ap.add_argument("--min-faithfulness", type=float, default=0.75)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    qs = json.loads(args.questions.read_text(encoding="utf-8"))
    if args.sample:
        qs = random.Random(7).sample(qs, min(args.sample, len(qs)))
    pipe = HttpPipeline(args.api) if args.api else None
    report = evaluate_pipeline(get_settings(), qs, args.mode, pipe=pipe)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    m = report["metrics"]
    print(
        f"mode={report['mode']} n={report['n']}  "
        + "  ".join(f"{k}={v}" for k, v in m.items() if not k.startswith("offline_"))
    )
    if args.gate and m["faithfulness"] < args.min_faithfulness:
        print(f"GATE FAILED: faithfulness {m['faithfulness']} < {args.min_faithfulness}", file=sys.stderr)
        raise SystemExit(1)
    if args.gate:
        print(f"GATE OK: faithfulness {m['faithfulness']} >= {args.min_faithfulness} (mode={report['mode']})")


if __name__ == "__main__":
    main()
