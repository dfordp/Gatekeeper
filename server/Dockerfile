FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Create uploads directory
RUN mkdir -p uploads

# Expose port
EXPOSE 8000

# ✓ PRODUCTION: Use Gunicorn + 4 Uvicorn workers (NOT --reload)
# Configuration:
# - 4 workers for 8-core system (load balance across cores)
# - 120s timeout (prevents hangs from freezing the app)
# - graceful-timeout 30s (clean shutdown of workers)
# - max-requests 1000 (recycle workers to prevent memory leaks)
# - max-requests-jitter 100 (stagger recycling to avoid thundering herd)
# - keep-alive 65s (HTTP keep-alive)
CMD ["gunicorn", \
     "--workers", "4", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--bind", "0.0.0.0:8000", \
     "--timeout", "120", \
     "--graceful-timeout", "30", \
     "--max-requests", "1000", \
     "--max-requests-jitter", "100", \
     "--keep-alive", "65", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "main:app"]