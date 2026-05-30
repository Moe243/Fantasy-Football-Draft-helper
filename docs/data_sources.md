# Data sources

This app uses a small set of **honest** integrations. Keys in `.env` only enable what is actually wired.

## Required for full mock-draft signals

| Source | Env var | Notes |
|--------|---------|--------|
| Sleeper players | _(none)_ | Public `api.sleeper.app/v1` — import from Setup |
| Rankings / projections | _(import)_ | `POST /api/rankings/import/csv` with `source_name` such as `fantasypros` or `espn` |

## Optional enhancements

| Source | Env var | Notes |
|--------|---------|--------|
| The Odds API | `ODDS_API_KEY` | Game lines via `POST /api/integrations/odds/import`; player props need event id + often a paid tier |
| Sleeper projections | _(none)_ | Unofficial `api.sleeper.app/projections/nfl/{season}/{week}` — `POST /api/integrations/sleeper/projections/import` |

## Placeholders (not live fantasy APIs)

- `ESPN_API_KEY` — no public ESPN fantasy API. Export ranks from ESPN or FantasyPros and import JSON with `source_name = espn`.
- `DRAFTKINGS_API_KEY`, `FANDUEL_API_KEY`, `CAESARS_API_KEY`, `DRAFT365_API_KEY` — stubs only. Props are aggregated through The Odds API bookmakers when configured.

## ESPN rankings workflow

1. Export or copy rankings into JSON rows (`player_name`, `position`, `team`, `overall_rank`, `projected_points`, …).
2. Open **Setup → Rankings JSON**, set `source_name` to `espn`, paste rows, submit.
3. Use **Refresh Consensus** so best-available uses the new source.

## Refresh order (manual)

1. Refresh Sleeper players  
2. Import Sleeper projections (optional)  
3. Import odds / props if `ODDS_API_KEY` is set  
4. Import rankings (ESPN / FantasyPros CSV or JSON)

Check status: `GET /api/setup/data-sources`
