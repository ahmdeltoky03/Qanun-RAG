# Experiment log

> **Scope of this grid (read before interpreting `embedding`).** This is an *offline structural*
> grid: it tunes `chunk_size`, `chunk_overlap` and `rerank` using the deterministic `hashing`
> proxy embedder, so the 12 runs are cheap and reproducible without a GPU or the model tunnel.
> The `embedding` column (`hashing-256` / `hashing-512`) is a **proxy knob, not the production
> model** — serving uses the multilingual `bge-m3` (1024-dim). The authoritative quality numbers
> for the real stack live in `reports/latest_eval.json` (`config.embedding = bge-m3`).
> The structural conclusions that *do* transfer: `rerank=lexical` beats `none` on every metric,
> and `chunk_size=300` wins — both are what production actually runs.

| run | chunk_size | chunk_overlap | embedding | rerank | chunks | hit_at_1 | hit_at_k | mrr | context_recall | faithfulness | oos_accuracy | seconds |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 4 | 300 | 60 | hashing-512 | lexical | 3450 | 0.5926 | 0.7593 | 0.662 | 0.7593 | 0.9638 | 0.5 | 14.1 |
| 2 | 300 | 60 | hashing-256 | lexical | 3450 | 0.5556 | 0.7593 | 0.6435 | 0.7593 | 0.9638 | 0.5 | 13.9 |
| 8 | 900 | 120 | hashing-512 | lexical | 2337 | 0.537 | 0.7407 | 0.6219 | 0.7407 | 0.964 | 0.5 | 10.5 |
| 6 | 900 | 120 | hashing-256 | lexical | 2337 | 0.537 | 0.7222 | 0.6173 | 0.7222 | 0.964 | 0.5 | 10.2 |
| 10 | 1500 | 120 | hashing-256 | lexical | 2298 | 0.537 | 0.7222 | 0.6173 | 0.7222 | 0.964 | 0.5 | 9.4 |
| 12 | 1500 | 120 | hashing-512 | lexical | 2298 | 0.537 | 0.7222 | 0.6157 | 0.7222 | 0.964 | 0.5 | 11.5 |
| 3 | 300 | 60 | hashing-512 | none | 3450 | 0.5 | 0.7407 | 0.6019 | 0.7407 | 0.9287 | 0.0 | 14.6 |
| 7 | 900 | 120 | hashing-512 | none | 2337 | 0.5 | 0.6852 | 0.5833 | 0.6852 | 0.9295 | 0.0 | 9.7 |
| 11 | 1500 | 120 | hashing-512 | none | 2298 | 0.5 | 0.6852 | 0.5833 | 0.6852 | 0.9295 | 0.0 | 11.5 |
| 1 | 300 | 60 | hashing-256 | none | 3450 | 0.463 | 0.7037 | 0.5602 | 0.7037 | 0.9288 | 0.0 | 13.3 |
| 5 | 900 | 120 | hashing-256 | none | 2337 | 0.463 | 0.6667 | 0.5494 | 0.6667 | 0.9295 | 0.0 | 9.4 |
| 9 | 1500 | 120 | hashing-256 | none | 2298 | 0.463 | 0.6667 | 0.5494 | 0.6667 | 0.9295 | 0.0 | 8.7 |

**Best by MRR:** run 4 (chunk_size=300, embedding=hashing-512, rerank=lexical, MRR=0.662).
