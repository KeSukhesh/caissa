"""StockfishAdapter — EnginePort implementation via python-chess UCI.

Stockfish runs as a separate process (UCI). This is the standard, license-clean
arrangement (GPL engine behind a process boundary; nothing is statically linked).

Prefer a fixed `depth` (or nodes) limit for reproducible accuracy numbers — the
same reason Lichess uses a node limit. See game-review-build-spec.md.
"""

from __future__ import annotations

import chess
import chess.engine

from app.config import settings
from app.core.ports import Line


class StockfishAdapter:
    def __init__(self, path: str | None = None) -> None:
        self._path = path or settings.stockfish_path

    def analyse(self, fen: str, *, multipv: int, depth: int) -> list[Line]:
        board = chess.Board(fen)
        # One short-lived engine process per call for the skeleton. A real
        # deployment keeps a pooled set of long-lived engines (see worker.py /
        # the "fishnet-style worker pool" in the architecture doc).
        with chess.engine.SimpleEngine.popen_uci(self._path) as engine:
            engine.configure(
                {"Threads": settings.engine_threads, "Hash": settings.engine_hash_mb}
            )
            infos = engine.analyse(
                board,
                chess.engine.Limit(depth=depth),
                multipv=multipv,
            )

        lines: list[Line] = []
        for info in infos:
            score = info["score"].pov(board.turn)  # side-to-move POV
            pv = [m.uci() for m in info.get("pv", [])]
            lines.append(
                Line(
                    move=pv[0] if pv else "",
                    cp=score.score(),  # None if mate
                    mate=score.mate(),  # None if cp
                    pv=pv,
                    depth=info.get("depth", depth),
                )
            )
        return lines
