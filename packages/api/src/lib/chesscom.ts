/**
 * chess.com Published-Data API client (read-only, no key).
 *
 * Light I/O on the request path (game import). Heavy compute (analysis) stays in
 * the Python service. PubAPI rule: serial access is unlimited; send a descriptive
 * User-Agent so they can reach us before blocking. Docs:
 * https://www.chess.com/announcements/view/published-data-api
 */

const UA =
	"Caissa/0.1 (personal chess trainer; contact: github.com/KeSukhesh/caissa)";

export type ChessComGame = {
	url: string;
	pgn: string;
	time_control: string;
	time_class: string; // bullet | blitz | rapid | daily
	rules: string; // "chess" for standard
	end_time: number; // epoch seconds
	rated: boolean;
	uuid?: string;
	white: ChessComPlayer;
	black: ChessComPlayer;
	eco?: string; // an opening URL, not the ECO code
};

type ChessComPlayer = {
	username: string;
	rating: number;
	result: string; // "win" | "checkmated" | "resigned" | "timeout" | "agreed" | ...
};

const DRAW_RESULTS = new Set([
	"agreed",
	"repetition",
	"stalemate",
	"insufficient",
	"50move",
	"timevsinsufficient",
]);

export async function fetchArchives(username: string): Promise<string[]> {
	const res = await fetch(
		`https://api.chess.com/pub/player/${encodeURIComponent(username.toLowerCase())}/games/archives`,
		{ headers: { "User-Agent": UA, Accept: "application/json" } },
	);
	if (res.status === 404) return [];
	if (!res.ok) throw new Error(`chess.com archives: HTTP ${res.status}`);
	const data = (await res.json()) as { archives: string[] };
	return data.archives ?? [];
}

/** Fetch one monthly archive of games. `archiveUrl` comes from fetchArchives(). */
export async function fetchArchiveGames(
	archiveUrl: string,
): Promise<ChessComGame[]> {
	const res = await fetch(archiveUrl, {
		headers: { "User-Agent": UA, Accept: "application/json" },
	});
	if (!res.ok) throw new Error(`chess.com archive: HTTP ${res.status}`);
	const data = (await res.json()) as { games: ChessComGame[] };
	return data.games ?? [];
}

/** Map a chess.com game + the importing username into our `game` row shape. */
export function mapChessComGame(g: ChessComGame, username: string) {
	const lower = username.toLowerCase();
	const color: "white" | "black" =
		g.white.username.toLowerCase() === lower ? "white" : "black";

	const result =
		g.white.result === "win"
			? "1-0"
			: g.black.result === "win"
				? "0-1"
				: "1/2-1/2";

	const me = color === "white" ? g.white : g.black;
	const userResult: "win" | "loss" | "draw" =
		me.result === "win" ? "win" : DRAW_RESULTS.has(me.result) ? "draw" : "loss";

	// ECO code from the PGN headers (the JSON `eco` field is a URL).
	const ecoMatch = g.pgn.match(/\[ECO\s+"([^"]+)"\]/);

	return {
		source: "chesscom" as const,
		sourceGameId: g.url,
		pgn: g.pgn,
		color,
		result,
		userResult,
		eco: ecoMatch?.[1] ?? null,
		whitePlayer: g.white.username,
		blackPlayer: g.black.username,
		whiteElo: g.white.rating ?? null,
		blackElo: g.black.rating ?? null,
		timeControl: g.time_control,
		timeClass: g.time_class,
		playedAt: g.end_time ? new Date(g.end_time * 1000) : null,
	};
}
