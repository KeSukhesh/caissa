import { relations } from "drizzle-orm";
import {
	index,
	integer,
	jsonb,
	pgTable,
	text,
	timestamp,
	unique,
	uuid,
} from "drizzle-orm/pg-core";

import { user } from "./auth";

// --- Linked external accounts (for game import + incremental-sync watermark) ---

export const linkedChessAccount = pgTable(
	"linked_chess_account",
	{
		id: uuid("id").primaryKey().defaultRandom(),
		userId: text("user_id")
			.notNull()
			.references(() => user.id, { onDelete: "cascade" }),
		platform: text("platform").$type<"chesscom" | "lichess">().notNull(),
		username: text("username").notNull(),
		// Epoch ms of the most-recent game we've imported (incremental sync).
		lastSyncedAt: timestamp("last_synced_at"),
		createdAt: timestamp("created_at").defaultNow().notNull(),
	},
	(t) => [unique("linked_account_uq").on(t.userId, t.platform, t.username)],
);

// --- Games (a user's own finished games) ---

export const game = pgTable(
	"game",
	{
		id: uuid("id").primaryKey().defaultRandom(),
		userId: text("user_id")
			.notNull()
			.references(() => user.id, { onDelete: "cascade" }),
		source: text("source").$type<"chesscom" | "lichess" | "pgn">().notNull(),
		// Stable id from the source (chess.com game url / lichess id). Null for pasted PGN.
		sourceGameId: text("source_game_id"),
		pgn: text("pgn").notNull(),
		// The user's colour in this game (null if unknown, e.g. some pasted PGNs).
		color: text("color").$type<"white" | "black">(),
		result: text("result"), // raw PGN result: "1-0" | "0-1" | "1/2-1/2" | "*"
		userResult: text("user_result").$type<"win" | "loss" | "draw">(),
		eco: text("eco"),
		opening: text("opening"),
		whitePlayer: text("white_player"),
		blackPlayer: text("black_player"),
		whiteElo: integer("white_elo"),
		blackElo: integer("black_elo"),
		timeControl: text("time_control"),
		timeClass: text("time_class"), // bullet | blitz | rapid | daily
		playedAt: timestamp("played_at"),
		createdAt: timestamp("created_at").defaultNow().notNull(),
	},
	(t) => [
		index("game_user_idx").on(t.userId),
		index("game_user_played_idx").on(t.userId, t.playedAt),
		// Dedupe imports by source id (per user).
		unique("game_source_uq").on(t.userId, t.source, t.sourceGameId),
	],
);

// --- Analysis (one Game Review per game) ---

export type MoveEval = {
	ply: number;
	san: string;
	cp: number | null;
	mate: number | null;
	// chess.com-style label; filled by the classifier (Sprint 1 pipeline).
	classification:
		| "brilliant"
		| "great"
		| "best"
		| "excellent"
		| "good"
		| "book"
		| "inaccuracy"
		| "mistake"
		| "blunder"
		| null;
	bestMove: string | null; // UCI
	winPctBefore: number | null;
	winPctAfter: number | null;
};

export const analysis = pgTable(
	"analysis",
	{
		id: uuid("id").primaryKey().defaultRandom(),
		gameId: uuid("game_id")
			.notNull()
			.references(() => game.id, { onDelete: "cascade" })
			.unique(),
		status: text("status")
			.$type<"pending" | "running" | "done" | "error">()
			.default("pending")
			.notNull(),
		engineDepth: integer("engine_depth"),
		accuracyWhite: integer("accuracy_white"), // 0-100, stored x100? keep 0-100 int for now
		accuracyBlack: integer("accuracy_black"),
		estimatedEloWhite: integer("estimated_elo_white"),
		estimatedEloBlack: integer("estimated_elo_black"),
		moves: jsonb("moves").$type<MoveEval[]>(),
		summary: jsonb("summary").$type<Record<string, unknown>>(),
		error: text("error"),
		createdAt: timestamp("created_at").defaultNow().notNull(),
		updatedAt: timestamp("updated_at")
			.defaultNow()
			.$onUpdate(() => new Date())
			.notNull(),
	},
	(t) => [index("analysis_game_idx").on(t.gameId)],
);

// --- Jobs (the queue — claimed by the Python worker via FOR UPDATE SKIP LOCKED) ---

export const job = pgTable(
	"job",
	{
		id: uuid("id").primaryKey().defaultRandom(),
		type: text("type").notNull(), // analyze_game | import_games | rebuild_insights | ...
		payload: jsonb("payload").$type<Record<string, unknown>>().notNull(),
		priority: integer("priority").default(0).notNull(), // higher = sooner
		status: text("status")
			.$type<"pending" | "running" | "done" | "error">()
			.default("pending")
			.notNull(),
		attempts: integer("attempts").default(0).notNull(),
		maxAttempts: integer("max_attempts").default(5).notNull(),
		lockedAt: timestamp("locked_at"),
		error: text("error"),
		createdAt: timestamp("created_at").defaultNow().notNull(),
		updatedAt: timestamp("updated_at")
			.defaultNow()
			.$onUpdate(() => new Date())
			.notNull(),
	},
	(t) => [index("job_status_priority_idx").on(t.status, t.priority)],
);

// --- Eval cache (tier 1 of the 3-tier eval lookup; keyed by normalized FEN) ---

export const evalCache = pgTable("eval_cache", {
	// First 4 FEN fields (placement, side, castling, ep) — move counters dropped.
	normalizedFen: text("normalized_fen").primaryKey(),
	eval: jsonb("eval").$type<Record<string, unknown>>().notNull(),
	depth: integer("depth"),
	source: text("source").$type<"lichess_dump" | "cloud_eval" | "stockfish">(),
	createdAt: timestamp("created_at").defaultNow().notNull(),
});

// --- Relations ---

export const gameRelations = relations(game, ({ one }) => ({
	user: one(user, { fields: [game.userId], references: [user.id] }),
	analysis: one(analysis, { fields: [game.id], references: [analysis.gameId] }),
}));

export const analysisRelations = relations(analysis, ({ one }) => ({
	game: one(game, { fields: [analysis.gameId], references: [game.id] }),
}));
