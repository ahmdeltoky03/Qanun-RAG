"""Distil a slow cross-encoder teacher into a small, fast student re-ranker (needs sentence-transformers; GPU recommended).

Teacher : BAAI/bge-reranker-v2-m3  (accurate, ~570M params)
Student : cross-encoder/mmarco-mMiniLMv2-L12-H384-v1 (multilingual, ~118M params)

The student is trained to reproduce the teacher's scores on (question, article) pairs built from the
corpus, so no human labels are needed. Evaluate teacher / student / no-rerank with
    QANUN_RERANK=cross-encoder QANUN_CROSS_ENCODER_MODEL=<model-or-dir> qanun-eval --out reports/eval_<name>.json
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path


def build_pairs(corpus: Path, questions: Path, per_q: int = 12, seed: int = 7) -> list[tuple[str, str]]:
    random.seed(seed)
    recs = [r for r in json.loads(corpus.read_text(encoding="utf-8")) if not r["is_repealed"]]
    qs = [q["question"] for q in json.loads(questions.read_text(encoding="utf-8"))]
    pairs = []
    for q in qs:
        for r in random.sample(recs, per_q):  # includes many negatives: the teacher scores them low
            pairs.append((q, r["text_ar"] if any("\u0600" <= c <= "\u06ff" for c in q) else r["text_en"]))
    return pairs


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--teacher", default="BAAI/bge-reranker-v2-m3")
    ap.add_argument("--student", default="cross-encoder/mmarco-mMiniLMv2-L12-H384-v1")
    ap.add_argument("--out", default="models/reranker-student")
    ap.add_argument("--epochs", type=int, default=2)
    args = ap.parse_args()
    from sentence_transformers import InputExample
    from sentence_transformers.cross_encoder import CrossEncoder
    from torch.utils.data import DataLoader

    pairs = build_pairs(Path("data/processed/civil_code.json"), Path("data/eval/questions.json"))
    teacher_scores = CrossEncoder(args.teacher).predict(pairs, batch_size=32, show_progress_bar=True)
    data = [InputExample(texts=list(p), label=float(s)) for p, s in zip(pairs, teacher_scores, strict=True)]
    student = CrossEncoder(args.student, num_labels=1)
    student.fit(train_dataloader=DataLoader(data, shuffle=True, batch_size=16), epochs=args.epochs, warmup_steps=50, output_path=args.out)
    print("saved student to", args.out)


if __name__ == "__main__":
    main()
