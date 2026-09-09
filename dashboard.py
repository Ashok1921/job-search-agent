"""
dashboard.py — Job Search Agent: Streamlit dashboard (Tracker UI)

Two tabs:
    1. Job Feed        — browse scored jobs, shortlist ones you like
                          (inserts into `applications` as 'not_applied')
    2. My Applications  — update status on shortlisted jobs; status_history
                          is auto-logged by the Postgres triggers already
                          set up on the `applications` table.

Env vars expected (.env file):
    DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD

Run:
    streamlit run dashboard.py
"""

import os
import pandas as pd
import psycopg2
import psycopg2.extras
import streamlit as st
from dotenv import load_dotenv
from db_config import get_db_conn

load_dotenv()

STATUS_OPTIONS = [
    "not_applied",
    "applied",
    "viewed",
    "interview_scheduled",
    "interviewing",
    "offer",
    "rejected",
    "withdrawn",
]

st.set_page_config(page_title="Job Search Agent", layout="wide")


@st.cache_resource
def get_cached_conn():
    return get_db_conn()


def run_query(query, params=None):
    conn = get_cached_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(query, params or ())
        return cur.fetchall()


def run_write(query, params=None):
    conn = get_cached_conn()
    with conn:
        with conn.cursor() as cur:
            cur.execute(query, params or ())


def fetch_job_feed(min_score: float):
    rows = run_query(
        """
        SELECT j.id, j.title, j.company_name, j.location, j.is_remote,
               j.fit_score, j.embedding_score, j.llm_score, j.score_rationale,
               j.apply_link, j.posted_at,
               (a.id IS NOT NULL) AS shortlisted
        FROM jobs j
        LEFT JOIN applications a ON a.job_id = j.id
        WHERE j.fit_score >= %s
        ORDER BY j.fit_score DESC;
        """,
        (min_score,),
    )
    return rows


def fetch_applications():
    rows = run_query(
        """
        SELECT a.id AS application_id, a.current_status, a.applied_at, a.notes,
               j.id AS job_id, j.title, j.company_name, j.location,
               j.fit_score, j.apply_link
        FROM applications a
        JOIN jobs j ON j.id = a.job_id
        ORDER BY a.updated_at DESC;
        """
    )
    return rows


def shortlist_job(job_id: int):
    run_write(
        """
        INSERT INTO applications (job_id, current_status)
        VALUES (%s, 'not_applied')
        ON CONFLICT (job_id) DO NOTHING;
        """,
        (job_id,),
    )


def update_status(application_id: int, new_status: str):
    applied_at_clause = ", applied_at = COALESCE(applied_at, now())" if new_status == "applied" else ""
    run_write(
        f"""
        UPDATE applications
        SET current_status = %s{applied_at_clause}
        WHERE id = %s;
        """,
        (new_status, application_id),
    )


def fetch_status_history(application_id: int):
    return run_query(
        """
        SELECT old_status, new_status, changed_by, note, changed_at
        FROM status_history
        WHERE application_id = %s
        ORDER BY changed_at DESC;
        """,
        (application_id,),
    )


st.title("🎯 Job Search Agent")

tab_feed, tab_apps = st.tabs(["📋 Job Feed", "📌 My Applications"])

# ------------------------------------------------------------------
# TAB 1: Job Feed
# ------------------------------------------------------------------
with tab_feed:
    min_score = st.slider("Minimum fit score", 0, 100, 70, step=5)
    jobs = fetch_job_feed(min_score)

    st.caption(f"{len(jobs)} job(s) with fit_score ≥ {min_score}")

    for job in jobs:
        with st.container(border=True):
            col_main, col_action = st.columns([5, 1])

            with col_main:
                remote_tag = " · Remote" if job["is_remote"] else ""
                st.markdown(f"**{job['title']}** — {job['company_name']}")
                st.caption(f"{job['location'] or ''}{remote_tag}  |  Fit score: **{job['fit_score']:.1f}**  (embedding {job['embedding_score']:.1f} / LLM {job['llm_score']:.1f})")
                if job["score_rationale"]:
                    st.write(job["score_rationale"])
                if job["apply_link"]:
                    st.markdown(f"[Apply link]({job['apply_link']})")

            with col_action:
                if job["shortlisted"]:
                    st.success("Shortlisted")
                else:
                    if st.button("Shortlist", key=f"shortlist_{job['id']}"):
                        shortlist_job(job["id"])
                        st.rerun()

# ------------------------------------------------------------------
# TAB 2: My Applications
# ------------------------------------------------------------------
with tab_apps:
    apps = fetch_applications()
    st.caption(f"{len(apps)} shortlisted job(s)")

    for app in apps:
        with st.container(border=True):
            col_main, col_status = st.columns([4, 2])

            with col_main:
                st.markdown(f"**{app['title']}** — {app['company_name']}")
                st.caption(f"{app['location'] or ''}  |  Fit score: {app['fit_score']:.1f}")
                if app["apply_link"]:
                    st.markdown(f"[Apply link]({app['apply_link']})")
                if app["notes"]:
                    st.write(f"Notes: {app['notes']}")

            with col_status:
                current = app["current_status"]
                new_status = st.selectbox(
                    "Status",
                    STATUS_OPTIONS,
                    index=STATUS_OPTIONS.index(current),
                    key=f"status_{app['application_id']}",
                )
                if new_status != current:
                    if st.button("Update", key=f"update_{app['application_id']}"):
                        update_status(app["application_id"], new_status)
                        st.rerun()

            with st.expander("Status history"):
                history = fetch_status_history(app["application_id"])
                if history:
                    df = pd.DataFrame(history)
                    st.dataframe(df, use_container_width=True, hide_index=True)
                else:
                    st.caption("No history yet.")