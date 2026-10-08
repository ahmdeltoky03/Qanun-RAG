#!/bin/bash
# set -e

# echo "Running database migrations..."
# cd /app/models/db_schemas/minirag/
# alembic upgrade head
# cd /app

set -e

echo "Waiting for PostgreSQL to be ready..."
until nc -z pgvector 5432; do
  echo "Waiting for pgvector database connection..."
  sleep 2
done

echo "PostgreSQL is up - running migrations..."
cd /app/models/db_schemas/minirag/
alembic upgrade head || echo "Alembic migration failed or already up to date."
cd /app

echo "Starting FastAPI app..."
exec "$@"

