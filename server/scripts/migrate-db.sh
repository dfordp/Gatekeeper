#!/bin/bash
# server/scripts/migrate-db.sh
# Run database migrations

set -e

echo "Running database initialization..."
python -c "from utils.database import init_db; init_db()"

echo "✓ Database initialized successfully"