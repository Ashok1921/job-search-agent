# Job Search Agent

An automated, AI-scored job search pipeline for the Indian GenAI/Agentic AI job market — pulls live listings, scores them against your resume, and helps you track applications like a mini ATS (Applicant Tracking System).

Built as a hands-on portfolio project by **Ashok D**, Generative AI & Agentic AI Developer.

**Repo:** https://github.com/Ashok1921/job-search-agent
**Live demo:** https://job-search-agent-clg2d4wufdwzxc5frayqng.streamlit.app/

---

## What it does

1. **Fetches** live job listings from JSearch (aggregates LinkedIn, Indeed, Naukri, Glassdoor via Google for Jobs)
2. **Scores** every listing against your resume using a hybrid approach — semantic embedding similarity + an LLM qualitative read — producing a single `fit_score` (0–100) with a plain-English rationale for each match
3. **Tracks** applications through a Streamlit dashboard — shortlist high-fit jobs, update status as you apply and hear back, with a full audit trail auto-logged in Postgres

---

## Screenshots

**Job Feed** — browse scored jobs above an adjustable fit threshold, with fit score breakdown and LLM rationale for each match:

![Job Feed](screenshots/job-feed.png)

**My Applications** — track status per shortlisted job, with full audit history auto-logged on every change:

![My Applications](screenshots/my-applications.png)

---

## Architecture

```
JSearch API (RapidAPI)
        │
        ▼
   fetcher.py  ──────►  jobs table (Postgres)
                              │
                              ▼
   scorer.py   ──────►  fit_score, embedding_score,
   (resume +                llm_score, rationale
    sentence-transformers        │
    + Gemini 2.5 Flash)          ▼
                          dashboard.py (Streamlit)
                              │
                    ┌─────────┴─────────┐
                    ▼                   ▼
              Job Feed tab      My Applications tab
           (browse + shortlist)  (status tracking,
                                  auto-logged history)
```

**Database:** 3 tables — `jobs`, `applications`, `status_history` — with Postgres triggers that automatically log every application status change, so the audit trail requires zero extra application code.

---

## Tech stack

| Layer | Choice |
|---|---|
| Job data source | [JSearch API](https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch) via RapidAPI |
| Language | Python |
| Database | PostgreSQL (local for dev, [Neon](https://neon.tech) for hosted/deployed) |
| Embeddings | `sentence-transformers` (`all-mpnet-base-v2`), local/free |
| LLM scoring | Google Gemini 2.5 Flash (`google-genai` SDK) |
| Dashboard | Streamlit |
| Deployment | Streamlit Community Cloud + Neon |

---

## Scoring methodology

Each job gets a blended `fit_score`:

```
fit_score = 0.4 × embedding_score + 0.6 × llm_score
```

- **`embedding_score`** — cosine similarity between resume text and job description embeddings. Fast, catches broad keyword/skill overlap.
- **`llm_score`** — Gemini 2.5 Flash reads the resume and job description together and rates fit 0–100, catching what embeddings miss: seniority mismatches, "fresher" vs. experienced-hire mislabeling, domain-specific requirements (e.g. mandatory cloud platform, specific programming language, years of experience).

LLM is weighted higher (60%) because it's the one that actually understands *why* something is or isn't a fit — e.g. correctly downgrading a Principal Engineer posting requiring 15+ years despite high keyword overlap with the resume.

---

## Project structure

```
job-search-agent/
├── db_config.py       # Shared DB connection (local Postgres or Neon via DATABASE_URL)
├── fetcher.py          # Pulls jobs from JSearch, upserts into `jobs` table
├── scorer.py           # Computes fit_score for unscored jobs
├── dashboard.py         # Streamlit app — Job Feed + My Applications
├── schema.sql           # Postgres schema (tables, triggers, indexes)
├── resume.txt            # Resume text used for embedding/LLM scoring
├── requirements.txt        # Deployment dependencies (Streamlit Cloud)
└── .env                     # Local secrets (not committed)
```

---

## Setup

### 1. Clone and install
```bash
git clone https://github.com/Ashok1921/job-search-agent.git
cd job-search-agent
python -m venv venv
venv\Scripts\activate        # Windows
pip install -r requirements.txt
pip install sentence-transformers google-genai requests   # for fetcher.py/scorer.py (local only)
```

### 2. Environment variables (`.env`)
```
RAPIDAPI_KEY=your_jsearch_rapidapi_key
GEMINI_API_KEY=your_gemini_api_key

# Local Postgres (default)
DB_HOST=localhost
DB_PORT=5432
DB_NAME=job_search_agent
DB_USER=postgres
DB_PASSWORD=your_password

# OR, to use hosted Neon instead of local:
# DATABASE_URL=postgresql://user:pass@host/dbname?sslmode=require
```

### 3. Create the database schema
```bash
createdb -U postgres job_search_agent
psql -U postgres -d job_search_agent -f schema.sql
```

### 4. Run the pipeline
```bash
python fetcher.py --query "Generative AI Developer in Hyderabad" --pages 2
python scorer.py --resume resume.txt --limit 20
python -m streamlit run dashboard.py
```

---

## Deployment

Deployed using the same free-tier pattern as [Autonomous AI Stock Agent](https://github.com/Ashok1921/Autonomous-aistock-agent):

- **Database:** Neon (hosted Postgres, free tier) — schema migrated via `pg_dump --schema-only --no-owner --no-privileges` + `psql`
- **App:** Streamlit Community Cloud, running only `dashboard.py`
- **Config:** `DATABASE_URL` set as a Streamlit secret, resolved by `db_config.py` ahead of local fallback
- **Lean deploy footprint:** `requirements.txt` deliberately excludes `sentence-transformers`/`google-genai` — those are only needed by `fetcher.py`/`scorer.py`, which run locally/on a schedule, not inside the deployed dashboard. Keeps the hosted app's memory footprint low on the free tier.

`fetcher.py` and `scorer.py` are run locally (or via a scheduled job) against Neon by temporarily setting `DATABASE_URL`, so the deployed dashboard always reflects fresh data without needing to host the heavier ML dependencies.

---

## Useful links

**Project**
- Repo: https://github.com/Ashok1921/job-search-agent
- Live app: https://job-search-agent-clg2d4wufdwzxc5frayqng.streamlit.app/

**Services this project depends on**
- JSearch API (RapidAPI) — manage `RAPIDAPI_KEY`: https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch
- Google AI Studio — manage `GEMINI_API_KEY`: https://aistudio.google.com/apikey
- Neon console — manage the hosted Postgres database: https://console.neon.tech
- Streamlit Community Cloud — manage the deployed app, secrets, logs: https://share.streamlit.io

**Local commands**
```bash
# Fetch new jobs
python fetcher.py --query "Generative AI Developer in Hyderabad" --pages 2

# Score unscored jobs
python scorer.py --resume resume.txt --limit 20

# Run dashboard locally (local Postgres)
python -m streamlit run dashboard.py

# Run dashboard locally, pointed at Neon
$env:DATABASE_URL="<your neon connection string>"
python -m streamlit run dashboard.py
```

---

## Known limitations

- Job descriptions from JSearch occasionally contain minor character-encoding artifacts (e.g. mis-rendered em-dashes) — cosmetic only, doesn't affect scoring.
- LLM scoring has some natural run-to-run variance (a few points) since it isn't a deterministic function — `fit_score` should be read as a strong directional signal, not an exact ranking.
- Currently single-resume, single-user by design — no multi-resume or multi-user support yet.

---

## Roadmap

- Scheduled daily/weekly Fetcher + Scorer runs so the feed stays fresh automatically
- Location/remote filters and sort options on the Job Feed
- Reminders/follow-up nudges based on `status_history` timestamps
