from celery import Celery

# Configure Celery to use Redis as the broker and result backend.
# Ensure Redis is running on localhost:6379.
app = Celery(
    'AyurAnkhTasks',
    broker='redis://localhost:6379/0',
    backend='redis://localhost:6379/1',
    include=['tasks'] # Tells Celery where to find our task functions
)

app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='Asia/Kolkata',
    enable_utc=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)

if __name__ == '__main__':
    app.start()