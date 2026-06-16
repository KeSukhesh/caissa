"""FastAPI entrypoint — thin HTTP shell.

No domain logic lives here. The TS app calls these endpoints; heavy work is
enqueued onto the Postgres `jobs` table and run by the worker (see worker.py).
Postgres is the integration boundary — results are written there and the TS app
reads them. (Sprint 0: endpoints are skeletons; `/debug/eval` works end-to-end
to verify the Stockfish wiring.)
"""

from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel

from app.adapters.stockfish import StockfishAdapter
from app.config import settings

app = FastAPI(title="Caïssa Analysis Service", version="0.0.1")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "caissa-analysis"}


class AnalyzeRequest(BaseModel):
    game_id: str


@app.post("/analyze", status_code=202)
def analyze(req: AnalyzeRequest) -> dict:
    """Enqueue a full Game Review for a stored game.

    TODO(Sprint 1): insert a row into the Postgres `jobs` table
    (type='analyze_game', payload={game_id}); the worker picks it up
    (SELECT ... FOR UPDATE SKIP LOCKED), analyses each ply with the
    EvalCachePort, classifies + scores accuracy, and writes `analyses`.
    """
    return {"status": "queued", "game_id": req.game_id}


@app.get("/debug/eval")
def debug_eval(fen: str, depth: int | None = None, multipv: int | None = None) -> dict:
    """Quick wiring test: analyse a single FEN with Stockfish. Remove later."""
    engine = StockfishAdapter()
    lines = engine.analyse(
        fen,
        multipv=multipv or settings.multipv,
        depth=depth or settings.quick_depth,
    )
    return {"fen": fen, "lines": [line.__dict__ for line in lines]}
