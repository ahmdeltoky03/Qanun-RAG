.PHONY: setup corpus index run test lint eval gate experiments loadtest up down canary ui
PY ?= python
HOST ?= http://localhost:8000
USERS ?= 50

setup:        ## install everything needed to develop and run
	$(PY) -m pip install -e ".[dev,ui]"

corpus:       ## PDF -> data/processed/civil_code.json (validated)
	qanun-build-corpus

index:        ## embed the corpus and build the vector index
	qanun-ingest

run:          ## API on http://localhost:8000  (docs at /docs)
	uvicorn qanun.api.main:get_app --factory --port 8000

ui:           ## Streamlit chat UI on http://localhost:8501 (API must be running)
	QANUN_API_URL=http://localhost:8000 streamlit run ui/app.py

test:
	pytest

lint:
	ruff check src tests ui loadtest optimization && ruff format --check src tests

eval:         ## evaluate all 58 questions, writes reports/latest_eval.json
	qanun-eval

# Gate on the FULL question set: a fixed-seed 20-sample is an arbitrary, noisy slice
# (seed-7 scored 0.708 vs 0.783 on all 58) that fails on chance, not quality. The full set is
# reproducible AND statistically sound, and the 0.75 threshold is unchanged.
gate:         ## CI quality gate (exit 1 if faithfulness < 0.75)
	qanun-eval --gate --min-faithfulness 0.75

experiments:  ## 12-run chunking/embedding/rerank grid -> reports/experiments.md
	$(PY) -m qanun.eval.experiments

HOST ?= http://localhost:8000
USERS ?= 50

loadtest:     ## locust against $(HOST); for the free tunnel use: make loadtest USERS=5
	USERS=$(USERS) loadtest/run.sh $(HOST)

up:           ## full stack in Docker
	docker compose up --build -d

down:
	docker compose down

canary:       ## make canary PCT=10   (0 = rollback, 100 = promote)
	scripts/canary.sh $(PCT)
