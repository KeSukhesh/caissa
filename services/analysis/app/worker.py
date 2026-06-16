"""Job worker — polls the Postgres `jobs` table and runs analysis.

The queue IS the `jobs` table (scale-appropriate; no broker at one-user scale).
Claim rows with `FOR UPDATE SKIP LOCKED` so concurrent workers never
double-process. Priority column: interactive jobs (a game you just imported)
beat background jobs. See the vault architecture doc.

Sprint 0: skeleton loop + the claim query. Handlers land in Sprint 1+.
"""

from __future__ import annotations

import time

import psycopg

from app.config import settings

CLAIM_SQL = """
UPDATE jobs
SET status = 'running', locked_at = now(), attempts = attempts + 1
WHERE id = (
    SELECT id FROM jobs
    WHERE status = 'pending'
    ORDER BY priority DESC, created_at ASC
    FOR UPDATE SKIP LOCKED
    LIMIT 1
)
RETURNING id, type, payload;
"""


def handle(job_type: str, payload: dict) -> None:
    # TODO(Sprint 1+): dispatch by type.
    #   analyze_game      -> per-ply EvalCachePort -> classify -> accuracy -> analyses
    #   rebuild_insights  -> weakness/opening reports (Sprint 3)
    #   generate_puzzles  -> lichess-puzzler over the user's PGNs (Sprint 3)
    #   warm_opening_cache, generate_variation_tree (Sprint 5), ...
    raise NotImplementedError(f"no handler for job type: {job_type}")


def run() -> None:
    # TODO(Sprint 1): the `jobs` table is created by the TS Drizzle schema
    # (packages/db). Until it exists this loop will no-op/log.
    conn = psycopg.connect(settings.database_url, autocommit=True)
    while True:
        with conn.cursor() as cur:
            try:
                cur.execute(CLAIM_SQL)
                row = cur.fetchone()
            except psycopg.Error:
                row = None  # jobs table not created yet
        if row is None:
            time.sleep(settings.job_poll_interval)
            continue
        _id, job_type, payload = row
        try:
            handle(job_type, payload)
            # TODO: mark done
        except Exception:  # noqa: BLE001 — skeleton
            # TODO: backoff / dead-letter after N attempts
            pass


if __name__ == "__main__":
    run()
