.PHONY: help install dev test lint format clean docker-build docker-push deploy

help:
    @echo "Gatekeeper Backend - Available Commands"
    @echo "========================================"
    @echo "make install       - Install dependencies"
    @echo "make dev           - Run development server"
    @echo "make test          - Run tests"
    @echo "make lint          - Run linter (flake8)"
    @echo "make format        - Format code (black)"
    @echo "make clean         - Clean cache files"
    @echo "make docker-build  - Build Docker image"
    @echo "make docker-push   - Push Docker image to registry"
    @echo "make deploy        - Deploy to production"

install:
    python -m pip install --upgrade pip
    pip install -r requirements.txt

dev:
    docker-compose up -d
    python main.py

test:
    pytest tests/ -v --cov=. --cov-report=html

lint:
    flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics
    flake8 . --count --exit-zero --max-complexity=10 --max-line-length=120 --statistics

format:
    black . --line-length=120
    isort . --profile=black

clean:
    find . -type f -name '*.pyc' -delete
    find . -type d -name '__pycache__' -delete
    find . -type d -name '.pytest_cache' -delete
    find . -type d -name '.coverage' -delete
    find . -type d -name 'htmlcov' -delete

docker-build:
    docker build -t gatekeeper-api:latest -f Dockerfile .
    docker build -t gatekeeper-api:dev -f Dockerfile.dev .

docker-push:
    docker tag gatekeeper-api:latest your-registry/gatekeeper-api:latest
    docker push your-registry/gatekeeper-api:latest

deploy:
    @echo "Deploying Gatekeeper to production..."
    docker-compose -f docker-compose.yml up -d
    @echo "✓ Deployment complete"