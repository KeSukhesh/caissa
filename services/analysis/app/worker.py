"""Job worker — claims `analyze_game` jobs and runs the Game Review pipeline.

The queue IS the `job` table (no broker at this scale). Claim with FOR UPDATE
SKIP LOCKED, dispatch by type, write results to Postgres, mark done/error.

Run:
    python -m app.worker                 # daemon: poll forever
    python -m app.worker --max 2         # process up to 2 jobs then exit (testing)
    python -m app.worker --max 2 --depth 14 --multipv 3
"""

from __future__ import annotations

import argparse
import time
import traceback

from app import db
from app.adapters.eval_cache import EvalCache
from app.adapters.stockfish import StockfishAdapter
from app.config import settings
from app.core.analysis import review_game


def handle_analyze_game(conn, payload: dict, *, depth: int, multipv: int) -> None:
    game_id = payload["gameId"]
    g = db.get_game(conn, game_id)
    if g is None:
        raise ValueError(f"game {game_id} not found")
    # One engine process for the whole game (fast); cache shared across positions.
    with StockfishAdapter() as engine:
        cache = EvalCache(engine, conn, multipv=multipv, depth=depth)
        result = review_game(g["pgn"], cache.get_lines)
    db.save_analysis(conn, game_id, depth, result)


def process_one(conn, *, depth: int, multipv: int) -> bool:
    job = db.claim_job(conn)
    if job is None:
        return False
    jid, jtype, payload = job["id"], job["type"], job["payload"]
    try:
        if jtype == "analyze_game":
            handle_analyze_game(conn, payload, depth=depth, multipv=multipv)
        else:
            raise ValueError(f"unknown job type: {jtype}")
        db.finish_job(conn, jid, "done")
        print(f"✓ job {jid} ({jtype})")
    except Exception as e:  # noqa: BLE001 — worker must survive any single job
        db.finish_job(conn, jid, "error", error=str(e))
        if isinstance(payload, dict) and payload.get("gameId"):
            db.fail_analysis(conn, payload["gameId"], str(e))
        print(f"✗ job {jid} ({jtype}): {e}")
        traceback.print_exc()
    return True


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=0, help="process at most N jobs then exit (0 = forever)")
    ap.add_argument("--depth", type=int, default=settings.deep_depth)
    ap.add_argument("--multipv", type=int, default=settings.multipv)
    args = ap.parse_args()

    conn = db.connect()
    processed = 0
    while True:
        did = process_one(conn, depth=args.depth, multipv=args.multipv)
        if did:
            processed += 1
            if args.max and processed >= args.max:
                break
        elif args.max:  # bounded mode: stop when the queue drains
            break
        else:
            time.sleep(settings.job_poll_interval)
    print(f"done; processed {processed} job(s)")


if __name__ == "__main__":
    main()
