"""Service configuration.

Loaded from env vars (see .env.example). The DATABASE_URL must point at the
same Postgres the TS app uses — Postgres is the integration boundary between
the two services (see the vault architecture doc: "Postgres is the source of
truth and the integration boundary").
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Shared Postgres (same DB as the TS monorepo's packages/db).
    database_url: str = "postgresql://postgres:password@localhost:5432/caissa"

    # Path to the Stockfish binary (UCI). Install via `brew install stockfish`
    # (macOS) or apt (Docker image installs it). Invoked as a separate process.
    stockfish_path: str = "stockfish"

    # Analysis defaults (Game Review — see game-review-build-spec.md).
    # MultiPV >= 2 is required for only-move / 2nd-line gap (Great detection).
    multipv: int = 3
    # Analyse to a fixed NODE budget (not depth) so effort is consistent across
    # positions of varying complexity → reproducible accuracy numbers. This is
    # what Lichess does (≈2.25M nodes for NNUE Stockfish). See game-review-build-spec.md.
    deep_nodes: int = 2_250_000  # pass 2: authoritative review
    quick_nodes: int = 200_000  # pass 1: instant provisional (future two-pass)
    quick_depth: int = 13  # depth fallback (used only by /debug/eval)
    engine_threads: int = 1  # single thread → deterministic per node budget
    engine_hash_mb: int = 128

    # Lichess cloud-eval fast path (tier 2 of the 3-tier eval cache).
    cloud_eval_url: str = "https://lichess.org/api/cloud-eval"

    # Worker loop poll interval (seconds) for the Postgres `jobs` table.
    job_poll_interval: float = 1.0


settings = Settings()
