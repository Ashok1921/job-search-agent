-- =========================================================
-- Job Search Agent — Postgres Schema
-- Tables: jobs, applications, status_history
-- =========================================================

-- Optional: keep everything in its own schema
-- CREATE SCHEMA IF NOT EXISTS job_search;
-- SET search_path TO job_search;

-- ---------------------------------------------------------
-- ENUM types
-- ---------------------------------------------------------

CREATE TYPE application_status AS ENUM (
    'not_applied',
    'applied',
    'viewed',
    'interview_scheduled',
    'interviewing',
    'offer',
    'rejected',
    'withdrawn'
);

CREATE TYPE job_source AS ENUM (
    'linkedin',
    'indeed',
    'naukri',
    'glassdoor',
    'google_jobs',
    'other'
);

-- ---------------------------------------------------------
-- jobs
-- One row per unique job listing pulled by the Fetcher agent
-- ---------------------------------------------------------

CREATE TABLE jobs (
    id                  BIGSERIAL PRIMARY KEY,

    -- JSearch identifiers (dedup key)
    external_job_id     TEXT NOT NULL,          -- job_id field from JSearch
    source              job_source NOT NULL DEFAULT 'other',

    -- Core listing data
    title               TEXT NOT NULL,
    company_name        TEXT NOT NULL,
    location            TEXT,
    is_remote           BOOLEAN DEFAULT FALSE,
    employment_type     TEXT,                   -- e.g. FULLTIME, CONTRACTOR
    description         TEXT,                   -- full JD text, used for embeddings

    -- Compensation (nullable — often missing)
    salary_min          NUMERIC(12,2),
    salary_max          NUMERIC(12,2),
    salary_currency     TEXT,

    -- Links & dates
    apply_link          TEXT NOT NULL,
    posted_at           TIMESTAMPTZ,
    fetched_at          TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- Scorer agent output
    fit_score           NUMERIC(5,2),           -- 0-100 blended score
    embedding_score      NUMERIC(5,2),          -- raw cosine similarity component
    llm_score            NUMERIC(5,2),          -- raw LLM qualitative component
    score_rationale      TEXT,                   -- short LLM explanation of the score
    scored_at            TIMESTAMPTZ,

    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE (external_job_id, source)
);

CREATE INDEX idx_jobs_fit_score ON jobs (fit_score DESC);
CREATE INDEX idx_jobs_posted_at ON jobs (posted_at DESC);
CREATE INDEX idx_jobs_company ON jobs (company_name);

-- ---------------------------------------------------------
-- applications
-- One row per job you've decided to track/apply to
-- (created by Tracker agent, usually once fit_score clears a threshold
--  or you manually mark interest)
-- ---------------------------------------------------------

CREATE TABLE applications (
    id                  BIGSERIAL PRIMARY KEY,
    job_id              BIGINT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,

    current_status      application_status NOT NULL DEFAULT 'not_applied',

    applied_at          TIMESTAMPTZ,
    resume_version      TEXT,                   -- which resume/tailoring variant was used
    cover_note          TEXT,                    -- optional tailored note/summary sent

    notes               TEXT,                    -- freeform tracking notes

    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE (job_id)                              -- one application record per job
);

CREATE INDEX idx_applications_status ON applications (current_status);

-- ---------------------------------------------------------
-- status_history
-- Append-only audit trail of every status change on an application
-- ---------------------------------------------------------

CREATE TABLE status_history (
    id                  BIGSERIAL PRIMARY KEY,
    application_id      BIGINT NOT NULL REFERENCES applications(id) ON DELETE CASCADE,

    old_status          application_status,
    new_status          application_status NOT NULL,
    changed_by          TEXT NOT NULL DEFAULT 'tracker_agent',  -- or 'user'
    note                TEXT,

    changed_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_status_history_application ON status_history (application_id, changed_at DESC);

-- ---------------------------------------------------------
-- Trigger: keep applications.updated_at fresh + auto-log to status_history
-- ---------------------------------------------------------

CREATE OR REPLACE FUNCTION fn_applications_status_audit()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();

    IF TG_OP = 'UPDATE' AND OLD.current_status IS DISTINCT FROM NEW.current_status THEN
        INSERT INTO status_history (application_id, old_status, new_status)
        VALUES (NEW.id, OLD.current_status, NEW.current_status);
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_applications_status_audit
BEFORE UPDATE ON applications
FOR EACH ROW
EXECUTE FUNCTION fn_applications_status_audit();

-- Also log the very first status on insert
CREATE OR REPLACE FUNCTION fn_applications_status_audit_insert()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO status_history (application_id, old_status, new_status, note)
    VALUES (NEW.id, NULL, NEW.current_status, 'initial status');
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_applications_status_audit_insert
AFTER INSERT ON applications
FOR EACH ROW
EXECUTE FUNCTION fn_applications_status_audit_insert();