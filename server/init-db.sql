-- server/init-db.sql
-- PostgreSQL initialization script

-- Create extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_ticket_created_at ON ticket(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ticket_status ON ticket(status);
CREATE INDEX IF NOT EXISTS idx_ticket_company ON ticket(company_id);

-- Grant permissions
GRANT ALL PRIVILEGES ON DATABASE gatekeeper_db TO gatekeeper_user;