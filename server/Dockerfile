FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn uvicorn

# Copy application files
COPY . .

# Create uploads directory
RUN mkdir -p uploads

# Expose port
EXPOSE 8000

# PRODUCTION ENGINE:
# -w 9: Spawns 9 worker processes (Optimal for 8-core VPS)
# -k uvicorn.workers.UvicornWorker: The bridge between Gunicorn and FastAPI
# --timeout 120: Gives OpenAI/Qdrant enough time for heavy requests
CMD ["gunicorn", "main:app", \
     "-w", "9", \
     "-k", "uvicorn.workers.UvicornWorker", \
     "--bind", "0.0.0.0:8000", \
     "--timeout", "120", \
     "--keep-alive", "5", \
     "--access-logfile", "-"]
