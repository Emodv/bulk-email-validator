#!/bin/bash
set -e

# Start Celery worker in the background
celery -A main.celery_app worker --loglevel=info &

# Start FastAPI in the foreground
uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
