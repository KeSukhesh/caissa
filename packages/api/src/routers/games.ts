import { analysis, db, game, job, linkedChessAccount } from "@caissa/db";
import { TRPCError } from "@trpc/server";
import { Chess } from "chess.js";
import { and, desc, eq } from "drizzle-orm";
import { z } from "zod";

import { protectedProcedure, router } from "../index";
import {
	fetchArchiveGames,
	fetchArchives,
	mapChessComGame,
} from "../lib/chesscom";

const ANALYZE_PRIORITY = 10;

function parsePgnHeaders(pgn: string): Record<string, string> {
	const headers: Record<string, string> = {};
	for (const m of pgn.matchAll(/\[(\w+)\s+"([^"]*)"\]/g)) {
		headers[m[1] as string] = m[2] as string;
	}
	return headers;
}

function toInt(v: string | undefined): number | null {
	const n = Number(v);
	return v && Number.isFinite(n) ? n : null;
}

/** Insert a game (deduped) + its pending analysis + an analyze_game job, atomically. */
async function enqueueGame(
	values: typeof game.$inferInsert,
): Promise<string | null> {
	return db.transaction(async (tx) => {
		const [inserted] = await tx
			.insert(game)
			.values(values)
			.onConflictDoNothing({
				target: [game.userId, game.source, game.sourceGameId],
			})
			.returning({ id: game.id });
		if (!inserted) return null; // duplicate — skip
		await tx
			.insert(analysis)
			.values({ gameId: inserted.id, status: "pending" });
		await tx.insert(job).values({
			type: "analyze_game",
			payload: { gameId: inserted.id },
			priority: ANALYZE_PRIORITY,
		});
		return inserted.id;
	});
}

export const gamesRouter = router({
	/** Import a single pasted PGN. */
	importPgn: protectedProcedure
		.input(z.object({ pgn: z.string().min(1) }))
		.mutation(async ({ ctx, input }) => {
			try {
				new Chess().loadPgn(input.pgn); // validate legality
			} catch {
				throw new TRPCError({ code: "BAD_REQUEST", message: "Invalid PGN" });
			}
			const h = parsePgnHeaders(input.pgn);
			const result = h.Result ?? null;
			const dateStr = h.UTCDate ?? h.Date; // PGN: "YYYY.MM.DD"
			const playedAt = dateStr ? new Date(dateStr.replace(/\./g, "-")) : null;

			const id = await enqueueGame({
				userId: ctx.session.user.id,
				source: "pgn",
				sourceGameId: null,
				pgn: input.pgn,
				result,
				eco: h.ECO ?? null,
				opening: h.Opening ?? null,
				whitePlayer: h.White ?? null,
				blackPlayer: h.Black ?? null,
				whiteElo: toInt(h.WhiteElo),
				blackElo: toInt(h.BlackElo),
				timeControl: h.TimeControl ?? null,
				playedAt:
					playedAt && !Number.isNaN(playedAt.getTime()) ? playedAt : null,
			});
			return { gameId: id };
		}),

	/** Sync recent games from a chess.com username (latest month by default). */
	importFromChessCom: protectedProcedure
		.input(
			z.object({
				username: z.string().min(1),
				months: z.number().int().min(1).max(3).default(1),
			}),
		)
		.mutation(async ({ ctx, input }) => {
			const archives = await fetchArchives(input.username);
			if (archives.length === 0) {
				throw new TRPCError({
					code: "NOT_FOUND",
					message: `No chess.com games found for "${input.username}"`,
				});
			}
			// Most-recent months first.
			const recent = archives.slice(-input.months).reverse();
			let imported = 0;
			let seen = 0;
			for (const url of recent) {
				const games = await fetchArchiveGames(url); // serial (PubAPI rule)
				for (const g of games) {
					if (g.rules !== "chess") continue; // standard chess only
					seen++;
					const mapped = mapChessComGame(g, input.username);
					const id = await enqueueGame({
						userId: ctx.session.user.id,
						...mapped,
					});
					if (id) imported++;
				}
			}

			await db
				.insert(linkedChessAccount)
				.values({
					userId: ctx.session.user.id,
					platform: "chesscom",
					username: input.username,
					lastSyncedAt: new Date(),
				})
				.onConflictDoNothing({
					target: [
						linkedChessAccount.userId,
						linkedChessAccount.platform,
						linkedChessAccount.username,
					],
				});

			return { imported, seen, skipped: seen - imported };
		}),

	/** List the current user's games (most recent first). */
	list: protectedProcedure
		.input(
			z
				.object({ limit: z.number().int().min(1).max(100).default(50) })
				.optional(),
		)
		.query(async ({ ctx, input }) => {
			return db.query.game.findMany({
				where: eq(game.userId, ctx.session.user.id),
				orderBy: [desc(game.playedAt), desc(game.createdAt)],
				limit: input?.limit ?? 50,
				with: {
					analysis: {
						columns: { status: true, accuracyWhite: true, accuracyBlack: true },
					},
				},
			});
		}),

	/** Fetch one game (must belong to the user) with its full analysis. */
	get: protectedProcedure
		.input(z.object({ id: z.string().uuid() }))
		.query(async ({ ctx, input }) => {
			const row = await db.query.game.findFirst({
				where: and(eq(game.id, input.id), eq(game.userId, ctx.session.user.id)),
				with: { analysis: true },
			});
			if (!row) throw new TRPCError({ code: "NOT_FOUND" });
			return row;
		}),
});
