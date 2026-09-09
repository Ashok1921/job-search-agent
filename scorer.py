"""
scorer.py — Job Search Agent: Scorer step

For every unscored (or re-scoreable) row in `jobs`, computes a hybrid
fit_score:
    - embedding_score: cosine similarity between resume text and job
      description, using sentence-transformers (all-mpnet-base-v2)
    - llm_score: a 0-100 qualitative fit score + short rationale from
      Gemini 2.5 Flash
    - fit_score: weighted blend of the two (default 40% embedding, 60% LLM)

Env vars expected (.env file):
    DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD   - Postgres connection
    GEMINI_API_KEY                                     - Gemini API key

Usage:
    python scorer.py --resume resume.txt --limit 50
    python scorer.py --resume resume.txt --rescore-all
"""

import os
import sys
import argparse
import json
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer, util
from google import genai
from db_config import get_db_conn

load_dotenv()

EMBEDDING_MODEL_NAME = "all-mpnet-base-v2"
EMBED_WEIGHT = 0.4   # weight of embedding_score in the blended fit_score
LLM_WEIGHT = 0.6     # weight of llm_score in the blended fit_score

LLM_PROMPT_TEMPLATE = """You are screening a job listing against a candidate's resume for fit.

RESUME:
{resume}

JOB TITLE: {title}
COMPANY: {company}
JOB DESCRIPTION:
{description}

Rate the candidate's fit for this specific role from 0 to 100, considering
skills overlap, seniority match, and domain relevance (not just keyword
overlap). Respond ONLY with valid JSON, no markdown fences, no preamble:
{{"score": <integer 0-100>, "rationale": "<one or two sentence explanation>"}}
"""


def load_resume_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def fetch_unscored_jobs(conn, limit: int, rescore_all: bool):
    where_clause = "" if rescore_all else "WHERE fit_score IS NULL"
    query = f"""
        SELECT id, title, company_name, description
        FROM jobs
        {where_clause}
        ORDER BY fetched_at DESC
        LIMIT %s;
    """
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(query, (limit,))
        return cur.fetchall()


def compute_embedding_score(model, resume_text: str, job_description: str) -> float:
    if not job_description:
        return 0.0
    embeddings = model.encode([resume_text, job_description], convert_to_tensor=True)
    similarity = util.cos_sim(embeddings[0], embeddings[1]).item()
    # cosine similarity is -1..1, normalize to 0..100
    return max(0.0, min(100.0, (similarity + 1) / 2 * 100))


def compute_llm_score(client, resume_text: str, title: str, company: str, description: str) -> tuple[float, str]:
    prompt = LLM_PROMPT_TEMPLATE.format(
        resume=resume_text,
        title=title or "",
        company=company or "",
        description=(description or "")[:6000],  # keep prompt size sane
    )
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )
        raw = response.text.strip()
        raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        parsed = json.loads(raw)
        score = float(parsed.get("score", 0))
        rationale = parsed.get("rationale", "")
        return max(0.0, min(100.0, score)), rationale
    except Exception as e:
        print(f"  ! LLM scoring failed: {e}")
        return 0.0, "LLM scoring failed."


def update_job_score(conn, job_id: int, embedding_score: float, llm_score: float, fit_score: float, rationale: str):
    with conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE jobs
                SET embedding_score = %s,
                    llm_score = %s,
                    fit_score = %s,
                    score_rationale = %s,
                    scored_at = now()
                WHERE id = %s;
                """,
                (embedding_score, llm_score, fit_score, rationale, job_id),
            )


def main():
    parser = argparse.ArgumentParser(description="Score jobs against a resume")
    parser.add_argument("--resume", required=True, help="Path to resume text file")
    parser.add_argument("--limit", type=int, default=50, help="Max jobs to score this run")
    parser.add_argument("--rescore-all", action="store_true", help="Rescore jobs even if already scored")
    args = parser.parse_args()

    gemini_key = os.getenv("GEMINI_API_KEY")
    if not gemini_key:
        sys.exit("ERROR: GEMINI_API_KEY environment variable not set.")
    gemini_client = genai.Client(api_key=gemini_key)

    print(f"Loading embedding model ({EMBEDDING_MODEL_NAME})...")
    embed_model = SentenceTransformer(EMBEDDING_MODEL_NAME)

    resume_text = load_resume_text(args.resume)

    conn = get_db_conn()
    jobs = fetch_unscored_jobs(conn, args.limit, args.rescore_all)
    print(f"Found {len(jobs)} job(s) to score.\n")

    for job in jobs:
        print(f"Scoring [{job['id']}] {job['title']} @ {job['company_name']}")

        embedding_score = compute_embedding_score(embed_model, resume_text, job["description"])
        llm_score, rationale = compute_llm_score(
            gemini_client, resume_text, job["title"], job["company_name"], job["description"]
        )

        fit_score = round(EMBED_WEIGHT * embedding_score + LLM_WEIGHT * llm_score, 2)

        print(f"  embedding_score={embedding_score:.1f}  llm_score={llm_score:.1f}  fit_score={fit_score:.1f}")
        print(f"  rationale: {rationale}\n")

        update_job_score(conn, job["id"], embedding_score, llm_score, fit_score, rationale)

    conn.close()
    print("Done.")


if __name__ == "__main__":
    main()