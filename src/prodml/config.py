"""Central configuration (12-factor: everything comes from env vars / .env)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="PRODML_", extra="ignore")

    # data
    corpus_path: Path = Path("data/processed/civil_code.json")
    index_dir: Path = Path("data/index")  # local Qdrant storage (baked into the Docker image)
    qdrant_url: str | None = None  # set to use a Qdrant server instead of local storage
    collection: str = "civil_code"

    # chunking (experiment knobs)
    chunk_size: int = 300  # max chars per chunk (best of the 12-run grid, see reports/experiments.md)
    chunk_overlap: int = 60

    # embeddings: hashing | cohere | openai | sentence-transformers
    embedding_provider: str = "hashing"
    embedding_model: str = "embed-multilingual-v3.0"
    embedding_dim: int = 512  # used by "hashing"; real providers report their own
    embedding_api_key: str | None = None
    embedding_base_url: str | None = None

    # retrieval
    top_k: int = 4
    candidate_k: int = 16
    min_score: float = 0.0  # min dense similarity of the best hit (set per embedding model)
    min_coverage: float = 0.25  # min idf-weighted share of query terms found in the best article
    dense_weight: float = 0.5  # RRF weight of the dense ranking (BM25 gets 1 - this)
    rerank: str = "lexical"  # none (dense only) | lexical (dense+BM25 hybrid) | cross-encoder (hybrid + rerank)
    cross_encoder_model: str = "BAAI/bge-reranker-v2-m3"

    # generation: fake | openai (any OpenAI-compatible server: vLLM, Ollama, OpenAI)
    llm_provider: str = "fake"
    llm_base_url: str = "http://vllm:8000/v1"
    llm_api_key: str = "EMPTY"
    llm_model: str = "Qwen/Qwen2.5-7B-Instruct-AWQ"
    llm_temperature: float = 0.0
    llm_max_tokens: int = 512
    llm_timeout_s: float = 60.0

    # guardrails
    max_question_chars: int = 1000
    pii_mode: str = "mask"  # mask | block | off

    # observability
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_host: str = "http://langfuse:3000"
    eval_report_path: Path = Path("reports/latest_eval.json")
    drift_baseline_path: Path = Path("data/index/query_baseline.json")
    drift_window: int = 200

    release: str = "stable"  # stable | canary (shown in /health, useful behind nginx)


@lru_cache
def get_settings() -> Settings:
    return Settings()
