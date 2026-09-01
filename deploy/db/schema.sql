-- Extracted from DEPLOYMENT.md, used to auto-init the dev Postgres container.
CREATE TABLE IF NOT EXISTS doctors (
    id BIGSERIAL PRIMARY KEY,
    telegram_id BIGINT NOT NULL UNIQUE,
    full_name TEXT NOT NULL,
    email TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS tokens (
    token TEXT PRIMARY KEY,
    doctor_id INTEGER REFERENCES doctors(id),
    full_name TEXT NOT NULL,
    test_type TEXT NOT NULL,
    test_version VARCHAR NOT NULL DEFAULT '1.0',
    status VARCHAR NOT NULL DEFAULT 'pending',
    used BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    opened_at TIMESTAMPTZ,
    used_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ DEFAULT (NOW() + INTERVAL '90 days')
);

CREATE TABLE IF NOT EXISTS results (
    id BIGSERIAL PRIMARY KEY,
    submission_id UUID UNIQUE,
    token TEXT REFERENCES tokens(token),
    full_name TEXT NOT NULL,
    test_type TEXT NOT NULL,
    score INTEGER,
    severity TEXT,
    answers JSONB,
    status VARCHAR NOT NULL DEFAULT 'notified',
    ai_interpretation TEXT,
    scoring_time_ms INTEGER,
    ai_time_ms INTEGER,
    n8n_execution_id TEXT,
    completed_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS error_logs (
    id BIGSERIAL PRIMARY KEY,
    n8n_execution_id TEXT,
    workflow_name TEXT,
    node_name TEXT,
    error_message TEXT NOT NULL,
    error_stack TEXT,
    input_data JSONB,
    session_token TEXT,
    submission_id UUID,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_tokens_doctor_id ON tokens(doctor_id);
CREATE INDEX IF NOT EXISTS idx_tokens_status ON tokens(status);
CREATE INDEX IF NOT EXISTS idx_results_token ON results(token);
CREATE INDEX IF NOT EXISTS idx_results_submission_id ON results(submission_id);
