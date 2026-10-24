"""Corpus-derived question suggestions for the UI's quick-prompt chips.

Instead of a hand-written pool of a dozen questions, chips are generated from the metadata
of every indexed article (number + AR/EN topic/section labels), so they span the whole code
and — sampled without replacement per batch — do not repeat within a batch.
"""

from __future__ import annotations

import json
import random
from pathlib import Path


class Suggester:
    def __init__(self, corpus_path: Path):
        self._path = corpus_path
        self._rows: list[dict] | None = None

    def _load(self) -> list[dict]:
        if self._rows is None:
            recs = json.loads(self._path.read_text(encoding="utf-8"))
            self._rows = [
                {
                    "n": r["article_number"],
                    "repealed": r["is_repealed"],
                    "topic_ar": r.get("topic_ar", ""),
                    "section_ar": r.get("section_ar", ""),
                    "topic": r.get("topic", ""),
                    "section": r.get("section", ""),
                }
                for r in recs
            ]
        return self._rows

    def questions(self, n: int, rng: random.Random | None = None) -> list[str]:
        rng = rng or random.Random()
        rows = self._load()
        out: list[str] = []
        seen: set[str] = set()
        for _ in range(n * 20):  # guard against a pathological template/duplicate loop
            if len(out) >= n:
                break
            q = self._render(rng.choice(rows), rng)
            if q and q not in seen:
                seen.add(q)
                out.append(q)
        return out

    @staticmethod
    def _render(r: dict, rng: random.Random) -> str:
        n = r["n"]
        if rng.random() < 0.75:  # the UI is Arabic-first
            opts = [f"ماذا تقول المادة {n}؟", f"اشرحلي المادة {n} ببساطة"]
            if r["topic_ar"]:
                opts += [f"ما حكم {r['topic_ar']}؟", f"ما هي أحكام {r['topic_ar']}؟"]
            if r["section_ar"]:
                opts.append(f"ما هي قواعد {r['section_ar']}؟")
            if r["repealed"]:
                opts.append(f"هل المادة {n} ما زالت سارية أم ملغاة؟")
            return rng.choice(opts)
        opts = [f"What does Article {n} say?", f"Explain Article {n} in plain terms."]
        if r["topic"]:
            opts.append(f"What are the rules on {r['topic']}?")
        if r["section"]:
            opts.append(f"How does the Code regulate {r['section']}?")
        return rng.choice(opts)
