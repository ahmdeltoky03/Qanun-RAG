# Serving, optimisation and monitoring: results sheet

## Load test (measured here, offline stack: fake LLM, 1 worker)
| endpoint | requests | failures | p50 ms | p95 ms | p99 ms |
|---|---|---|---|---|---|
| /ask | 685 | 0 | 570 | 1500 | 3500 |
| /ask/stream | 127 | 0 | 160 | 880 | 2000 |
| /health | 75 | 0 | 130 | 700 | 1800 |
Re-run against the real stack: `loadtest/run.sh http://localhost:8080` (vLLM latency will dominate).

## Optimisation, before / after (TO FILL - needs GPU)
| config | faithfulness | answer_relevancy | context_precision | context_recall | p50 latency |
|---|---|---|---|---|---|
| fp16 generator, no re-ranker | | | | | |
| AWQ 4-bit generator | | | | | |
| + hybrid retrieval (measured offline: MRR 0.62 -> 0.66 vs dense-only) | | | | | |
| + distilled re-ranker | | | | | |
Commands: see `optimization/quantize_awq.py`, `optimization/distill_reranker.py`, `optimization/compare.py`.

## Monitoring
Alert rules and their unit tests: `monitoring/alerts.yml`, `monitoring/alerts_test.yml` (`promtool test rules`).
