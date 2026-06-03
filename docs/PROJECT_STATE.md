# Project State

Last reviewed: 2026-06-03

This file is the project's guardrail. Before changing draft, league, player, or practice-draft behavior, read this file and keep the listed expectations true unless the user explicitly changes the product direction.

## Current Goal

Build a local-first fantasy football draft helper that behaves like a real Sleeper-based draft room while keeping the existing simple stack:

- Python standard library backend
- SQLite database
- Vanilla HTML/CSS/JS frontend
- Sleeper as the base player and league data source
- JSON/CSV-style imports for rankings, projections, stats, and props when clean APIs are unavailable

Do not rebuild the app from scratch. Prefer small, focused changes.

## Current Working Surface

- App runs with `python3 -m backend.app.main`.
- Browser opens at `http://127.0.0.1:8787`.
- SQLite database lives at `.data/fantasy.db`.
- Sleeper players auto-load if missing or stale.
- `SAMPLE_PLAYERS` remains a fallback only when database players are unavailable.
- Setup tab imports Sleeper league data and shows draft order mapping.
- Draft Board tab uses backend draft state as the source of truth.
- Players tab searches real database players and opens player detail data when available.
- Mock Draft tab supports starting, simulating, picking, and resetting a saved practice draft.
- Waivers tab uses enriched Sleeper trending data when available.
- Chat tab is a simple route-backed assistant, not a full LLM tool layer yet.

## Important Current League Facts

Local database currently contains the imported Sleeper league:

- League: `No Guts, No Glory 26`
- League ID: `1315477281887506432`
- Season: `2026`
- Teams: `10`
- Active draft ID: `1315477281891708928`
- `yahia21` must be draft slot `10`, not slot `1`.
- Draft columns must be sorted by true Sleeper draft slot, not user order, roster order, or manager name.
- In a 10-team snake draft, slot 10 owns pick 10 in round 1 and pick 11 in round 2 before traded-pick adjustments.

## Source Of Truth Rules

- Sleeper draft metadata is the source of truth for draft slots.
- Use `draft_order` and `slot_to_roster_id` before any fallback ordering.
- Fallback ordering is allowed only when Sleeper metadata is missing, and the UI/API must expose a warning.
- Draft Board UI should render from `/api/draft/state` or `/api/draft/board`, not from stale frontend-only assumptions.
- Drafted players and keepers must be excluded from Best Available unless a UI mode explicitly asks to show them.
- Practice draft state must persist in SQLite across page refreshes.

## Must Not Regress

- Running `python3 -m backend.app.main` works.
- `GET /api/health` returns OK.
- `GET /api/players` returns database players when imported players exist.
- Importing a Sleeper league imports league, users, rosters, drafts, draft picks, traded picks when available, draft slots, and future pick ownership.
- The Setup tab shows draft mapping after league import.
- The Draft Board tab highlights current pick and my picks.
- Clicking Draft on a Best Available player assigns the current pick automatically.
- Simulate Next Pick and Simulate To My Pick update the board immediately.
- Players tab supports search, position, team, age, number, active, and sort filters.
- Provider adapters that are not configured return clear messages instead of crashing.

## Known Gaps

- Rankings/projections are still only as good as imported data or optional provider configuration.
- CSV file upload is not implemented yet; JSON paste/import is the current MVP path.
- Draft simulator AI is useful but still simple.
- Draft history and traded picks exist in the backend but need a stronger frontend inspection view.
- Notifications and weekly scheduled jobs are not implemented.
- No authentication or deployment hardening exists yet; this is a local MVP.
- Context7 is documented as a developer docs helper, but it is not available in every Codex session.

## Change Protocol

For every future change:

1. State the single goal of the change.
2. Identify the affected routes, services, frontend functions, and database tables.
3. Add or update a regression test for any bug being fixed.
4. Make the smallest code change that satisfies the goal.
5. Run the regression checklist in `docs/REGRESSION_CHECKLIST.md`.
6. Update this file when project behavior, known gaps, or critical facts change.
7. Commit only after the app is back to a known working state.
