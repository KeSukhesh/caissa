"""Ports (interfaces) for the analysis core.

Hexagonal / ports-&-adapters: the domain logic (classification, accuracy,
weakness clustering, puzzle gen, ...) depends ONLY on these Protocols, never on
Stockfish/Lichess/chess.com specifics. Each adapter lives in app/adapters/ and
is swappable + fake-testable. See the vault architecture doc.

Sprint 0: only EnginePort + EvalCachePort are needed (Game Review). The rest are
declared here as the contract for later sprints and left unimplemented.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Line:
    """One engine principal variation."""

    move: str  # UCI, e.g. "e2e4"
    cp: int | None  # centipawns from side-to-move POV (None if mate)
    mate: int | None  # mate-in-N (None if cp)
    pv: list[str]  # principal variation (UCI moves)
    depth: int


class EnginePort(Protocol):
    """Drive a UCI engine (Stockfish). MultiPV >= 2 for only-move detection."""

    def analyse(self, fen: str, *, multipv: int, depth: int) -> list[Line]: ...


class EvalCachePort(Protocol):
    """3-tier eval lookup: local cache -> Lichess cloud-eval -> own Stockfish.

    Returns the top `multipv` lines for a position, caching the result.
    """

    def get_eval(self, fen: str, *, multipv: int, depth: int) -> list[Line]: ...


# --- Declared for later sprints (not implemented in Sprint 0) -----------------


class GameSourcePort(Protocol):
    """Import a user's finished games (chess.com PubAPI / Lichess API)."""

    def fetch_games(self, username: str, *, since: int | None = None) -> list[str]: ...
    # returns PGNs; incremental via `since` watermark; dedupe by game id.


class PuzzleGenPort(Protocol):
    """Generate engine-verified puzzles from PGNs (à la lichess-puzzler). Sprint 3."""

    def generate(self, pgn: str) -> list[dict]: ...


class TaggerPort(Protocol):
    """Classify a position/mistake by tactical theme. Sprint 3."""

    def tag(self, fen: str, solution: list[str]) -> list[str]: ...


class HumanModelPort(Protocol):
    """Maia — predict the likely human move at a target Elo. Sprint 4."""

    def policy(self, fen: str, elo: int) -> dict[str, float]: ...


class TranscriptionPort(Protocol):
    """Whisper — batch voice -> text with word timestamps. Sprint 6+ (feature T)."""

    def transcribe(self, audio_path: str) -> list[dict]: ...
