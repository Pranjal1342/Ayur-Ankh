#!/bin/bash

# 1. Start the Celery worker in the background (& at the end)
# We use --pool=gevent or threads for better compatibility in limited free containers if needed, 
# but standard is usually okay. Let's stick to standard first.
celery -A celery_app worker --loglevel=info --concurrency=2 &

# 2. Start the FastAPI server in the foreground
# It MUST use $PORT to satisfy Render's free tier requirement.
uvicorn main:app --host 0.0.0.0 --port $PORT