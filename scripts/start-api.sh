#!/usr/bin/env bash
# Boot entrypoint for ephemeral-disk hosts (Render / Railway free tier).
#
# The vector index under data/index/ is gitignored, so on a fresh container it
# does not exist yet. Rebuild it once at boot from the committed corpus, then
# start the API. On the Docker image the index is baked in at build time, so the
# rebuild is skipped automatically (the folder already exists).
#
# Env:
#   PORT              listen port injected by the host (default 8000)
#   QANUN_INDEX_DIR   index location (default data/index, must match settings)
set -euo pipefail

INDEX_DIR="${QANUN_INDEX_DIR:-data/index}"

# Resolve the index path through the app settings so we never disagree with config.py.
INDEX_DIR="$(python -c 'from qanun.config import get_settings; print(get_settings().index_dir)' 2>/dev/null || echo "$INDEX_DIR")"

if [ ! -d "${INDEX_DIR}/qdrant" ]; then
  echo "[boot] no vector index at ${INDEX_DIR}/qdrant — building from corpus (one time)…"
  python -m qanun.ingest
else
  echo "[boot] vector index present at ${INDEX_DIR}/qdrant — skipping ingest."
fi

echo "[boot] starting API on 0.0.0.0:${PORT:-8000}"
exec uvicorn qanun.api.main:get_app --factory --host 0.0.0.0 --port "${PORT:-8000}"
