# Regression Checklist

Run this checklist before calling a draft-room, player-database, Sleeper import, or mock-draft change complete.

## Command Checks

From the repo root:

```bash
python3 -m unittest discover backend/tests
env PYTHONPYCACHEPREFIX=/private/tmp/codex-pycache python3 -m compileall backend
node --check frontend/app.js
node --check frontend/mock-draft-extensions.js
```

Then start the app:

```bash
python3 -m backend.app.main
```

Verify:

```bash
curl -s http://127.0.0.1:8787/api/health
curl -s http://127.0.0.1:8787/api/setup/status
```

Expected:

- Health returns `"ok": true`.
- Setup status shows Sleeper players loaded when the database has been seeded/imported.

## Browser Smoke Checks

Open `http://127.0.0.1:8787`.

Check:

- Navigation shows Draft Board, Players, Mock Draft, Waivers, Chat, and Setup.
- Players tab loads real database rows.
- Setup tab shows Sleeper league ID controls, My Team, Refresh Sleeper Players, data source controls, and draft order mapping.
- Draft Board tab loads without console-visible UI breakage.
- Mock Draft tab loads controls for Start, Simulate Next, Simulate To My Pick, and Reset.

## Sleeper League Checks

After importing league `1315477281887506432`:

- League name is `No Guts, No Glory 26`.
- Managers imported count is `10`.
- Draft slots count is `10`.
- Active draft ID is `1315477281891708928`.
- `yahia21` appears as draft slot `10`.
- Draft board columns are ordered by draft slot ascending.
- Round 1 slot 10 is pick 10.
- Round 2 slot 10 is pick 11.
- My selected team remains saved after refresh.

## Draft Room Checks

Check normal drafting:

- Current pick is highlighted.
- My picks are visually distinct.
- Best Available rows have Draft buttons.
- Clicking Draft does not ask for a pick number.
- The drafted player appears in the current pick cell.
- The drafted player disappears from Best Available.
- Current pick advances.
- My Upcoming Picks updates.
- Roster Needs updates.
- Refreshing the browser keeps practice draft state.

Check simulation:

- Simulate Next Pick updates the board immediately.
- Simulate To My Pick stops on the user's next pick.
- Reset Mock Draft clears practice picks and refreshes the board.

## Player Database Checks

Check Players tab filters:

- Search by name.
- Position filter.
- Team filter.
- Age min and max filters.
- Jersey number filter.
- Active only checkbox.
- Sort dropdown.
- View Details opens profile, rankings, stats/projections, props, news, and notes sections when data exists.

## Do Not Merge Or Commit If

- Any command check fails.
- The Draft Board uses alphabetical/user/roster order instead of true draft slots.
- `SAMPLE_PLAYERS` appears as the source while database players exist.
- Practice draft state is lost on browser refresh.
- A provider adapter crashes because an API key is missing.
- A frontend change requires manually typing normal draft picks again.
