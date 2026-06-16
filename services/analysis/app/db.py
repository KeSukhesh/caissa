"""Postgres access for the worker. The TS app and this service coordinate
through the shared DB (the integration boundary); the `job` table is the queue.
"""

from __future__ import annotations

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Json

from app.config import settings

# Claim the highest-priority pending job, locking it so concurrent workers
# never grab the same row (FOR UPDATE SKIP LOCKED).
CLAIM_SQL = """
UPDATE job SET status = 'running', locked_at = now(), attempts = attempts + 1
WHERE id = (
    SELECT id FROM job
    WHERE status = 'pending'
    ORDER BY priority DESC, created_at ASC
    FOR UPDATE SKIP LOCKED
    LIMIT 1
)
RETURNING id, type, payload;
"""


def connect() -> psycopg.Connection:
    return psycopg.connect(settings.database_url, autocommit=True, row_factory=dict_row)


def claim_job(conn: psycopg.Connection) -> dict | None:
    with conn.cursor() as cur:
        cur.execute(CLAIM_SQL)
        return cur.fetchone()


def get_game(conn: psycopg.Connection, game_id: str) -> dict | None:
    with conn.cursor() as cur:
        cur.execute("SELECT id, pgn FROM game WHERE id = %s", (game_id,))
        return cur.fetchone()


def save_analysis(conn: psycopg.Connection, game_id: str, depth: int, result: dict) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE analysis SET status='done', engine_depth=%s, accuracy_white=%s, "
            "accuracy_black=%s, moves=%s, summary=%s, error=NULL, updated_at=now() "
            "WHERE game_id=%s",
            (
                depth,
                result["accuracyWhite"],
                result["accuracyBlack"],
                Json(result["moves"]),
                Json(result["summary"]),
                game_id,
            ),
        )


def fail_analysis(conn: psycopg.Connection, game_id: str, error: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE analysis SET status='error', error=%s, updated_at=now() WHERE game_id=%s",
            (error[:500], game_id),
        )


def finish_job(
    conn: psycopg.Connection, job_id: str, status: str, error: str | None = None
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE job SET status=%s, error=%s, updated_at=now() WHERE id=%s",
            (status, error[:500] if error else None, job_id),
        )
