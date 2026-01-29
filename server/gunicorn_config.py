import multiprocessing
import os

# Server configuration
bind = "0.0.0.0:8000"
workers = max(1, multiprocessing.cpu_count())
worker_class = "uvicorn.workers.UvicornWorker"
worker_connections = 1000
max_requests = 1000
max_requests_jitter = 100

# Logging
accesslog = "-"
errorlog = "-"
loglevel = os.getenv("LOG_LEVEL", "info").lower()

# Timeouts
timeout = 120
graceful_timeout = 30

# Process naming
proc_name = "gatekeeper-api"

# Environment
env = {
    "PYTHONUNBUFFERED": "1",
}