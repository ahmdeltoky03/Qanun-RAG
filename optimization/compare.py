"""Print a before/after table from two qanun-eval reports.   python optimization/compare.py before.json after.json"""

import json
import sys

a, b = (json.load(open(p, encoding="utf-8")) for p in sys.argv[1:3])
print(f"| metric | {a['config']['llm']} | {b['config']['llm']} | delta |\n|---|---|---|---|")
for k in ("faithfulness", "answer_relevancy", "context_precision", "context_recall", "hit_at_k", "mrr", "p50_latency_ms"):
    if k in a["metrics"] and k in b["metrics"]:
        print(f"| {k} | {a['metrics'][k]} | {b['metrics'][k]} | {b['metrics'][k] - a['metrics'][k]:+.4f} |")
