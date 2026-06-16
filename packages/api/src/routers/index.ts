import { protectedProcedure, publicProcedure, router } from "../index";
import { gamesRouter } from "./games";

export const appRouter = router({
	healthCheck: publicProcedure.query(() => {
		return "OK";
	}),
	privateData: protectedProcedure.query(({ ctx }) => {
		return {
			message: "This is private",
			user: ctx.session.user,
		};
	}),
	games: gamesRouter,
});
export type AppRouter = typeof appRouter;
