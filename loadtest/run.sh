#!/usr/bin/env bash
# Load test: writes reports/locust_*.csv and reports/locust.html.
# Default profile is 50 users x 2m (for a self-hosted/vLLM backend with real replicas).
# Against the free single-worker Colab/ngrok tunnel, 50 users self-saturates it - lower the ramp:
#   USERS=5 RUNTIME=60s ./loadtest/run.sh http://localhost:8000
set -euo pipefail
HOST="${1:-http://localhost:8000}"  # matches `make run` (uvicorn :8000)
USERS="${USERS:-50}"
RUNTIME="${RUNTIME:-2m}"
locust -f loadtest/locustfile.py --host "$HOST" --headless -u "$USERS" -r 10 -t "$RUNTIME" --csv reports/locust --html reports/locust.html
