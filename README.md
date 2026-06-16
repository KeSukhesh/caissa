# Caïssa

> *Named for Caïssa, the goddess/muse of chess (Sir William Jones, 1763).*

A **personal chess coach that learns from your own games.** Connect your
chess.com / Lichess account → it analyses every game with Stockfish → finds the
mistakes *you* keep making → drills you on exactly those, explained in English.

**Sprint 1 (in progress): a standalone chess.com-style Game Review.** Everything
else (personalized weakness loop, Maia sparring, opening trainer, voice
think-aloud) builds on the same analysis surface and comes after.

📚 Full design lives in the vault — **read before building**:
`~/Projects/second-brain/projects/caissa/` → `product.md` (what & why),
`architecture.md` (how), `scope-and-roadmap.md` (sprints),
`game-review-build-spec.md` (Sprint 1 recipe).

## Locked decisions
- **Engine:** Stockfish, **server-side** (`python-chess` + UCI), from day one.
- **Source model:** **clean-room / closeable** — original code on MIT/BSD libs.
  Chesskit (AGPL) / freechess (GPL) / lila are **reference-only, do not copy code**
  (the Lichess win%/accuracy *formulas* are facts and fine to reimplement).
  Stockfish (GPL) stays behind the process boundary (UCI), not linked.
- **No multiplayer** (solo trainer). No Chrome extension.

## Architecture (two services + Postgres)
```
apps/web (Next.js) ──tRPC──▶ apps/server (Hono) ──┐
                                                  ├─▶ Postgres  (source of truth + cache + jobs)
        services/analysis (Python/FastAPI) ───────┘
        python-chess + Stockfish (ports & adapters); polls the jobs table
```
Postgres is the integration boundary: the TS app enqueues jobs + reads results;
the Python service writes analysis back. (See `architecture.md`.)

## Repo layout
```
apps/
  web/                Next.js frontend (review UI: board, eval bar/graph, glyphs)
  server/             Hono + tRPC API
packages/
  api/  auth/  db/  env/  ui/  config/    (Drizzle, Better-Auth, shadcn/ui, ...)
services/
  analysis/           Python FastAPI + python-chess + Stockfish (server-side engine)
```

## Getting started
```bash
pnpm install                 # TS monorepo deps
pnpm run db:start            # local Postgres (Docker)
pnpm run db:push             # apply Drizzle schema
pnpm run dev                 # web :3001, server :3000

# analysis service (separate) — see services/analysis/README.md
brew install stockfish
cd services/analysis && python3 -m venv .venv && source .venv/bin/activate
pip install -e . && cp .env.example .env
uvicorn app.main:app --reload --port 8000   # :8000
```

## Common scripts
`pnpm dev` · `pnpm build` · `pnpm check` (Biome) · `pnpm check-types` ·
`pnpm db:start | db:push | db:studio | db:stop`

## Status — Sprint 0 ✅ (scaffold)
Monorepo + analysis-service skeleton in place. **Next:** game import
(chess.com/Lichess API + PGN), then the Game Review pipeline
(Stockfish MultiPV → win% → classify + Brilliant/Great → accuracy → review UI)
per `game-review-build-spec.md`.

---
*Scaffolded with [Better-T-Stack](https://github.com/AmanVarshney01/create-better-t-stack).*
