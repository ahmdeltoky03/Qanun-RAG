"""Chunking / embedding / retrieval experiments, logged to CSV + Markdown (no tracking server needed).

python -m qanun.eval.experiments            # offline embedder grid (CI-safe)
QANUN_EMBEDDING_PROVIDER=cohere QANUN_EMBEDDING_API_KEY=... python -m qanun.eval.experiments
"""

from __future__ import annotations

import csv
import itertools
import json
import tempfile
import time
from pathlib import Path

from qanun.api.main import build_pipeline
from qanun.config import Settings, get_settings
from qanun.eval.run import evaluate_pipeline
from qanun.ingest import build_index

GRID = {
    "chunk_size": [300, 900, 1500],
    "embedding_dim": [256, 512],
    "rerank": ["none", "lexical"],
}
COLUMNS = [
    "run",
    "chunk_size",
    "chunk_overlap",
    "embedding",
    "rerank",
    "chunks",
    "hit_at_1",
    "hit_at_k",
    "mrr",
    "context_recall",
    "faithfulness",
    "oos_accuracy",
    "seconds",
]


def run_grid(base: Settings, questions: list[dict], out_dir: Path) -> list[dict]:
    rows = []
    for i, (cs, dim, rerank) in enumerate(itertools.product(*GRID.values()), start=1):
        with tempfile.TemporaryDirectory() as tmp:
            s = base.model_copy(
                update={
                    "index_dir": Path(tmp),
                    "chunk_size": cs,
                    "chunk_overlap": min(120, cs // 5),
                    "embedding_dim": dim,
                    "rerank": rerank,
                }
            )
            t0 = time.perf_counter()
            stats = build_index(s)
            rep = evaluate_pipeline(s, questions, mode="offline", pipe=build_pipeline(s))
            m = rep["metrics"]
            rows.append({
                "run": i, "chunk_size": cs, "chunk_overlap": s.chunk_overlap, "embedding": stats["embedding"], "rerank": rerank,
                "chunks": stats["chunks"], **{k: m[k] for k in ("hit_at_1", "hit_at_k", "mrr", "context_recall", "faithfulness", "oos_accuracy")},
                "seconds": round(time.perf_counter() - t0, 1),
            })  # fmt: skip
            print(rows[-1])
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "experiments.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(rows)
    best = max(rows, key=lambda r: (r["mrr"], r["hit_at_k"]))
    lines = ["# Experiment log", "", "| " + " | ".join(COLUMNS) + " |", "|" + "---|" * len(COLUMNS)]
    lines += ["| " + " | ".join(str(r[c]) for c in COLUMNS) + " |" for r in sorted(rows, key=lambda r: -r["mrr"])]
    lines += [
        "",
        f"**Best by MRR:** run {best['run']} (chunk_size={best['chunk_size']}, embedding={best['embedding']}, rerank={best['rerank']}, MRR={best['mrr']}).",
        "",
    ]
    (out_dir / "experiments.md").write_text("\n".join(lines), encoding="utf-8")
    (out_dir / "best_config.json").write_text(json.dumps(best, indent=2))
    return rows


def main() -> None:
    qs = json.loads(Path("data/eval/questions.json").read_text(encoding="utf-8"))
    run_grid(get_settings(), qs, Path("reports"))


if __name__ == "__main__":
    main()
