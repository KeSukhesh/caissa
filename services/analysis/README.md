# Caïssa — Analysis Service (Python)

Server-side chess analysis: **Stockfish + python-chess**, ports-&-adapters, FastAPI.
The TS monorepo calls this over HTTP; heavy work runs off a Postgres `jobs` table;
results are written back to the shared Postgres (the integration boundary).

> Design contract lives in the vault:
> `~/Projects/second-brain/projects/caissa/architecture.md` and
> `game-review-build-spec.md`. This is the **Sprint 0 skeleton**.

## Layout
```
app/
  main.py            FastAPI shell (/health, /analyze stub, /debug/eval works)
  worker.py          jobs-table poller (FOR UPDATE SKIP LOCKED) — handlers TODO
  config.py          settings (DATABASE_URL, STOCKFISH_PATH, analysis defaults)
  core/ports.py      Protocols: EnginePort, EvalCachePort (+ later-sprint ports)
  adapters/stockfish.py  StockfishAdapter (EnginePort via UCI)
```

## Run locally
```bash
brew install stockfish                 # macOS (or apt: apt-get install stockfish)
cd services/analysis
python3 -m venv .venv && source .venv/bin/activate
pip install -e .                       # or: uv pip install -e .
cp .env.example .env                   # point DATABASE_URL at the monorepo's Postgres
uvicorn app.main:app --reload --port 8000
# verify Stockfish wiring (startpos):
# curl 'http://localhost:8000/debug/eval?fen=rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR%20w%20KQkq%20-%200%201'
```

## License note
Caïssa is **clean-room / closeable**. Stockfish (GPL) is invoked as a separate
process via UCI (process boundary) — not linked into our code. All Python deps
here are permissive. Do **not** copy AGPL/GPL source (Chesskit/freechess/lila are
reference-only).
