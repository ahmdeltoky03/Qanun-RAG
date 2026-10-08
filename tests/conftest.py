from __future__ import annotations

import json
from pathlib import Path

import pytest

from prodml.config import Settings

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "data" / "processed" / "civil_code.json"


@pytest.fixture(scope="session")
def records() -> list[dict]:
    return json.loads(CORPUS.read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def settings(tmp_path_factory) -> Settings:
    return Settings(
        corpus_path=CORPUS,
        index_dir=tmp_path_factory.mktemp("index"),
        embedding_provider="hashing",
        llm_provider="fake",
        drift_baseline_path=tmp_path_factory.mktemp("drift") / "baseline.json",
        eval_report_path=tmp_path_factory.mktemp("rep") / "e.json",
    )


@pytest.fixture(scope="session")
def pipeline(settings):
    from prodml.api.main import build_pipeline
    from prodml.ingest import build_index

    build_index(settings)
    return build_pipeline(settings)


@pytest.fixture(scope="session")
def client(pipeline, settings):
    from fastapi.testclient import TestClient

    from prodml.api.main import create_app

    with TestClient(create_app(pipeline, settings)) as c:
        yield c
