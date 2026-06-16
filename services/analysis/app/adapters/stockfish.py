"""StockfishAdapter — EnginePort implementation via python-chess UCI.

Stockfish runs as a separate process (UCI) — the standard, license-clean
arrangement (GPL engine behind a process boundary; nothing statically linked).

Use as a context manager to keep ONE engine process alive across a whole game
(open once, analyse every position, close) — far faster than spawning per call:

    with StockfishAdapter() as engine:
        lines = engine.analyse(board, multipv=3, depth=18)

Used outside a context (e.g. /debug/eval), it opens and closes per call.
Prefer a fixed depth (or nodes) for reproducible accuracy numbers.
"""

from __future__ import annotations

import chess
import chess.engine

from app.config import settings
from app.core.ports import Line


class StockfishAdapter:
    def __init__(self, path: str | None = None) -> None:
        self._path = path or settings.stockfish_path
        self._engine: chess.engine.SimpleEngine | None = None

    def __enter__(self) -> StockfishAdapter:
        self._engine = chess.engine.SimpleEngine.popen_uci(self._path)
        self._engine.configure(
            {"Threads": settings.engine_threads, "Hash": settings.engine_hash_mb}
        )
        return self

    def __exit__(self, *_exc) -> None:
        if self._engine is not None:
            self._engine.quit()
            self._engine = None

    def analyse(self, board: chess.Board | str, *, multipv: int, depth: int) -> list[Line]:
        if isinstance(board, str):
            board = chess.Board(board)

        own = self._engine is None
        engine = self._engine or chess.engine.SimpleEngine.popen_uci(self._path)
        if own:
            engine.configure(
                {"Threads": settings.engine_threads, "Hash": settings.engine_hash_mb}
            )
        try:
            infos = engine.analyse(board, chess.engine.Limit(depth=depth), multipv=multipv)
        finally:
            if own:
                engine.quit()

        lines: list[Line] = []
        for info in infos:
            score = info["score"].pov(board.turn)  # side-to-move POV
            pv = [m.uci() for m in info.get("pv", [])]
            lines.append(
                Line(
                    move=pv[0] if pv else "",
                    cp=score.score(),
                    mate=score.mate(),
                    pv=pv,
                    depth=info.get("depth", depth),
                )
            )
        return lines
