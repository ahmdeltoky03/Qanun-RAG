#!/usr/bin/env bash
# 50 concurrent users, 2 minutes. Writes reports/locust_*.csv and reports/locust.html
set -euo pipefail
HOST="${1:-http://localhost:8080}"
locust -f loadtest/locustfile.py --host "$HOST" --headless -u 50 -r 10 -t 2m --csv reports/locust --html reports/locust.html
