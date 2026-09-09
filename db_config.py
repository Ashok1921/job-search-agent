"""
db_config.py — Shared Postgres connection config for the Job Search Agent.

Connection resolution order:
    1. DATABASE_URL env var (full connection string) — used for Neon or
       any other hosted Postgres. Set this in Streamlit Cloud secrets or
       your local .env when you want to point at Neon.
    2. Individual DB_HOST / DB_PORT / DB_NAME / DB_USER / DB_PASSWORD env
       vars — used for local Postgres (the default for local dev).

Usage (in fetcher.py, scorer.py, dashboard.py):
    from db_config import get_db_conn
    conn = get_db_conn()
"""

import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

# Fallback: on Streamlit Community Cloud, secrets are primarily accessed via
# st.secrets rather than os.environ. Streamlit does auto-sync flat top-level
# secrets into os.environ, but we check st.secrets explicitly too so this
# works even if that behavior changes.
if not DATABASE_URL:
    try:
        import streamlit as st
        DATABASE_URL = st.secrets.get("DATABASE_URL")
    except Exception:
        pass  # not running under Streamlit, or no secrets configured

LOCAL_DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": os.getenv("DB_PORT", "5432"),
    "dbname": os.getenv("DB_NAME", "job_search_agent"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", ""),
}


def get_db_conn():
    """Returns a psycopg2 connection — Neon if DATABASE_URL is set, else local."""
    if DATABASE_URL:
        return psycopg2.connect(DATABASE_URL, sslmode="require")
    return psycopg2.connect(**LOCAL_DB_CONFIG)


def using_neon() -> bool:
    return bool(DATABASE_URL)