#!/bin/bash

# Use 'python -m' to guarantee it finds the installed modules
python -m celery -A celery_app worker --loglevel=info --concurrency=2 &

# Start uvicorn the same way
python -m uvicorn main:app --host 0.0.0.0 --port $PORT