"""Game Review analysis — pure logic (no I/O).

Clean-room reimplementation of the documented Lichess formulas (win% from
centipawns, per-move accuracy, harmonic + volatility-weighted game accuracy) +
a first-pass chess.com-style Brilliant/Great heuristic. See the vault's
game-review-build-spec.md. These are math/ideas, not copied code.

`review_game(pgn, eval_fn)` takes an `eval_fn(board) -> list[Line]` (top lines
from the side-to-move POV, best first) and returns the per-move report.
"""

from __future__ import annotations

import io
import math
import statistics
from dataclasses import dataclass, field

import chess
import chess.pgn

from app.core.ports import Line

PIECE_VALUES = {
    chess.PAWN: 1,
    chess.KNIGHT: 3,
    chess.BISHOP: 3,
    chess.ROOK: 5,
    chess.QUEEN: 9,
    chess.KING: 0,
}

# Win%-loss thresholds (in win-percentage points) for move classification.
T_EXCELLENT, T_GOOD, T_INACCURACY, T_MISTAKE = 2.0, 5.0, 10.0, 20.0

# Brilliant/Great gating (kept deliberately strict — these should be RARE).
CRIT_LO, CRIT_HI = 15.0, 85.0  # position must be genuinely undecided
GREAT_GAP = 20.0  # 2nd-best move must drop >=20% (i.e. the only move avoiding a serious error)
BRILLIANT_MIN_SAC = 2  # net material invested (pawns) after the best line settles
SAC_PV_PLIES = 8  # settle material over this many plies of the engine's best continuation
MIN_SPECIAL_PLY = 8  # no Brilliant/Great in the opening (proxy until book detection)


def win_pct(cp: int | None, mate: int | None) -> float:
    """Win% (0..100) for the side the score is measured for. Lichess constant."""
    if mate is not None:
        return 100.0 if mate > 0 else 0.0
    c = max(-1000, min(1000, cp if cp is not None else 0))
    return 50.0 + 50.0 * (2.0 / (1.0 + math.exp(-0.00368208 * c)) - 1.0)


def move_accuracy(win_before: float, win_after: float) -> float:
    """Per-move accuracy (0..100) from the mover's win% drop. Lichess formula."""
    diff = max(0.0, win_before - win_after)
    acc = 103.1668 * math.exp(-0.04354 * diff) - 3.1669
    return max(0.0, min(100.0, acc))


def material_balance(board: chess.Board, color: chess.Color) -> int:
    return sum(
        val * (len(board.pieces(pt, color)) - len(board.pieces(pt, not color)))
        for pt, val in PIECE_VALUES.items()
    )


@dataclass
class _Rec:
    win_mover: float  # win% for the side to move
    white_win: float  # win% from White's POV (for the volatility series)
    best_move: str | None
    gap: float  # win% gap best vs 2nd-best (mover POV) → only-move signal
    cp_white: int | None
    mate_white: int | None
    pv: list[str] = field(default_factory=list)  # best line's principal variation (UCI)


def _evaluate(board: chess.Board, eval_fn) -> _Rec:
    if board.is_checkmate():
        # Side to move is mated → it lost.
        white_win = 0.0 if board.turn == chess.WHITE else 100.0
        return _Rec(0.0, white_win, None, 0.0, None, -1 if board.turn == chess.WHITE else 1)
    if board.is_game_over(claim_draw=False) or board.is_stalemate():
        return _Rec(50.0, 50.0, None, 0.0, 0, None)

    lines: list[Line] = eval_fn(board)
    best = lines[0]
    wm = win_pct(best.cp, best.mate)
    gap = wm - win_pct(lines[1].cp, lines[1].mate) if len(lines) > 1 else 0.0
    white_win = wm if board.turn == chess.WHITE else 100.0 - wm
    if board.turn == chess.WHITE:
        cp_white, mate_white = best.cp, best.mate
    else:
        cp_white = -best.cp if best.cp is not None else None
        mate_white = -best.mate if best.mate is not None else None
    return _Rec(wm, white_win, best.move, gap, cp_white, mate_white, pv=best.pv)


def _is_sacrifice(board: chess.Board, move: chess.Move, continuation_pv: list[str]) -> bool:
    """True if the move genuinely INVESTS material — i.e. the mover is still down
    >= BRILLIANT_MIN_SAC after the engine's best continuation plays out. Settling
    over several plies (not just one reply) is what excludes combinations that win
    the material straight back, and simple recaptures."""
    mover = board.turn
    before = material_balance(board, mover)
    b = board.copy()
    b.push(move)
    for uci in continuation_pv[:SAC_PV_PLIES]:
        try:
            b.push(chess.Move.from_uci(uci))
        except (ValueError, AssertionError):
            break
    return (before - material_balance(b, mover)) >= BRILLIANT_MIN_SAC


def _classify(
    is_best: bool,
    loss: float,
    win_before: float,
    win_after: float,
    gap: float,
    sacrifice: bool,
    ply: int,
    is_recapture: bool,
) -> str:
    if is_best:
        # Brilliant/Great are deliberately rare: only on the best move, in a
        # genuinely undecided position, past the opening, and not a recapture.
        eligible = ply >= MIN_SPECIAL_PLY and CRIT_LO < win_before < CRIT_HI and not is_recapture
        if eligible and sacrifice and win_after >= 50.0:
            return "brilliant"  # sound material sacrifice that stays at least equal
        if eligible and gap >= GREAT_GAP:
            return "great"  # the only move avoiding a serious error
        return "best"
    if loss < T_EXCELLENT:
        return "excellent"
    if loss < T_GOOD:
        return "good"
    if loss < T_INACCURACY:
        return "inaccuracy"
    if loss < T_MISTAKE:
        return "mistake"
    return "blunder"


def _game_accuracy(white_win: list[float], move_accs: list[tuple[str, float]]) -> dict:
    """Per-side accuracy = mean(volatility-weighted mean, harmonic mean). Lichess."""
    n = len(white_win)
    window = max(2, min(8, n // 10))
    weights: list[float] = []
    for i in range(len(move_accs)):
        lo = max(0, i - window // 2)
        seg = white_win[lo : lo + window] or white_win[lo : lo + 1]
        weights.append(max(0.5, statistics.pstdev(seg) if len(seg) > 1 else 0.5))

    def for_color(color: str) -> int | None:
        accs = [a for (c, a), _ in zip(move_accs, weights) if c == color]
        ws = [w for (c, _), w in zip(move_accs, weights) if c == color]
        if not accs:
            return None
        weighted = sum(a * w for a, w in zip(accs, ws)) / sum(ws)
        harmonic = len(accs) / sum(1.0 / max(1.0, a) for a in accs)
        return round((weighted + harmonic) / 2.0)

    return {"white": for_color("white"), "black": for_color("black")}


def review_game(pgn: str, eval_fn) -> dict:
    """Analyse a full game. Returns moves[], accuracy per side, and a summary."""
    game = chess.pgn.read_game(io.StringIO(pgn))
    if game is None:
        raise ValueError("could not parse PGN")

    board = game.board()
    boards = [board.copy()]
    moves = list(game.mainline_moves())
    for mv in moves:
        board.push(mv)
        boards.append(board.copy())

    recs = [_evaluate(b, eval_fn) for b in boards]

    moves_out: list[dict] = []
    move_accs: list[tuple[str, float]] = []
    for i, mv in enumerate(moves):
        before, after = recs[i], recs[i + 1]
        mover_white = boards[i].turn == chess.WHITE
        win_before = before.win_mover
        win_after = 100.0 - after.win_mover  # convert opponent POV → mover POV
        loss = max(0.0, win_before - win_after)
        is_best = before.best_move is not None and mv.uci() == before.best_move
        is_recapture = (
            i > 0 and boards[i].is_capture(mv) and moves[i - 1].to_square == mv.to_square
        )
        # Settle material over the engine's best continuation FROM the resulting position.
        sac = _is_sacrifice(boards[i], mv, after.pv)
        cls = _classify(
            is_best, loss, win_before, win_after, before.gap, sac, i + 1, is_recapture
        )
        move_accs.append(("white" if mover_white else "black", move_accuracy(win_before, win_after)))
        moves_out.append(
            {
                "ply": i + 1,
                "san": boards[i].san(mv),
                "cp": after.cp_white,
                "mate": after.mate_white,
                "classification": cls,
                "bestMove": before.best_move,
                "winPctBefore": round(win_before, 1),
                "winPctAfter": round(win_after, 1),
            }
        )

    accuracy = _game_accuracy([r.white_win for r in recs], move_accs)
    counts: dict[str, dict[str, int]] = {"white": {}, "black": {}}
    for (color, _), m in zip(move_accs, moves_out):
        counts[color][m["classification"]] = counts[color].get(m["classification"], 0) + 1

    return {
        "moves": moves_out,
        "accuracyWhite": accuracy["white"],
        "accuracyBlack": accuracy["black"],
        "summary": {"counts": counts, "plies": len(moves_out)},
    }
