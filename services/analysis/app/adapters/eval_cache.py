"""EvalCache — the 3-tier eval lookup.

Sprint 1 implements tier 1 (local `eval_cache` table, keyed by normalized FEN)
and tier 3 (our Stockfish). Tier 2 (Lichess /api/cloud-eval) is deliberately
deferred: mixing a differently-tuned external eval into per-move classification
would make labels inconsistent across a game. Add it later as a pre-tier-3
fast-path for common positions. See architecture.md.
"""

from __future__ import annotations

import chess
from psycopg.types.json import Json

from app.core.ports import Line


def normalize_fen(fen: str) -> str:
    # First 4 FEN fields (placement, side, castling, en-passant); drop move counters
    # so transpositions share a cache entry. Side-to-move is encoded, so cached
    # mover-POV lines stay valid for the exact position.
    return " ".join(fen.split(" ")[:4])


class EvalCache:
    def __init__(self, engine, conn, *, multipv: int, depth: int) -> None:
        self.engine = engine
        self.conn = conn
        self.multipv = multipv
        self.depth = depth

    def get_lines(self, board: chess.Board) -> list[Line]:
        nfen = normalize_fen(board.fen())
        with self.conn.cursor() as cur:
            cur.execute("SELECT eval FROM eval_cache WHERE normalized_fen = %s", (nfen,))
            row = cur.fetchone()
        if row:
            cached = row["eval"]
            if cached.get("depth", 0) >= self.depth and cached.get("multipv", 0) >= self.multipv:
                return [Line(**ln) for ln in cached["lines"]][: self.multipv]

        lines = self.engine.analyse(board, multipv=self.multipv, depth=self.depth)
        payload = {
            "lines": [ln.__dict__ for ln in lines],
            "depth": self.depth,
            "multipv": self.multipv,
        }
        with self.conn.cursor() as cur:
            cur.execute(
                "INSERT INTO eval_cache (normalized_fen, eval, depth, source) "
                "VALUES (%s, %s, %s, 'stockfish') "
                "ON CONFLICT (normalized_fen) DO UPDATE SET eval = EXCLUDED.eval, depth = EXCLUDED.depth",
                (nfen, Json(payload), self.depth),
            )
        return lines
