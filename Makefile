.PHONY: setup corpus index run test lint eval gate experiments loadtest up down canary ui
PY ?= python

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

gate:         ## CI quality gate (exit 1 if faithfulness < 0.75)
	qanun-eval --sample 20 --gate --min-faithfulness 0.75

experiments:  ## 12-run chunking/embedding/rerank grid -> reports/experiments.md
	$(PY) -m qanun.eval.experiments

loadtest:     ## 50 users for 2 minutes against $(HOST)
	loadtest/run.sh $(HOST)

up:           ## full stack in Docker
	docker compose up --build -d

down:
	docker compose down

canary:       ## make canary PCT=10   (0 = rollback, 100 = promote)
	scripts/canary.sh $(PCT)
