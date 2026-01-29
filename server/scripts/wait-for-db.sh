#!/bin/bash
# server/scripts/wait-for-db.sh
# Wait for PostgreSQL to be ready

set -e

host="$1"
port="$2"
shift 2
cmd="$@"

echo "Waiting for PostgreSQL at $host:$port..."

until PGPASSWORD=$DB_PASSWORD psql -h "$host" -p "$port" -U "$DB_USER" -d "$DB_NAME" -c '\q'; do
  >&2 echo "PostgreSQL is unavailable - sleeping..."
  sleep 1
done

>&2 echo "PostgreSQL is up - executing command..."
exec $cmd