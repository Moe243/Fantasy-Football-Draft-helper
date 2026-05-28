# Context7 MCP Plan

Context7 is a developer documentation helper only. It should be used by future Codex work to verify current documentation before changing provider adapters, schema decisions, or architecture plans.

Context7 should not be used as a fantasy football data source. The app data should continue to come from Sleeper, rankings/projection imports, odds or props providers, ESPN/imported stats, and SQLite.

## When To Check Docs

Use Context7 before implementing or changing:

- Sleeper adapters for users, leagues, rosters, drafts, draft picks, players, traded picks, and previous seasons.
- ESPN adapters or ESPN-compatible imports.
- Sportsbook, odds, and props adapters for official APIs, licensed feeds, or aggregators.
- CSV/JSON import structures and source-specific mapping rules.
- SQLite schema changes and migration behavior.
- A future FastAPI migration.
- A future MCP server exposing app tools.

If Context7 is unavailable in a Codex session, fall back to official source documentation and record that fallback in the work summary.

## Data Source Boundary

Actual app data sources:

- Sleeper: base player identity, league settings, users, rosters, drafts, picks, trending players.
- Rankings/projection imports: FantasyPros, ESPN, Draft365, or other allowed CSV/JSON sources.
- Odds/props providers: official APIs, licensed feeds, or approved aggregators such as The Odds API.
- SQLite: local persistence for normalized player, league, ranking, stat, prop, news, draft, and practice state.

Do not scrape private or fragile endpoints without clearly marking them unofficial. Prefer official APIs, licensed feeds, user-provided CSV/JSON, or mock adapter interfaces.

## Future MCP Server Idea

This fantasy app could later expose MCP tools for assistants and other clients:

- `get_players`
- `get_player_detail`
- `get_consensus_rankings`
- `get_draft_board`
- `get_draft_recommendations`
- `get_waiver_risers`
- `simulate_practice_pick`

Those tools should call the app database and service layer. They should not call Context7 for fantasy data.
