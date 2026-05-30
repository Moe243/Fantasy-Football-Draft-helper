# Data Sources Setup

## The Odds API (game lines and player props)

1. Create an account at https://the-odds-api.com/
2. Copy your API key into `.env` as `ODDS_API_KEY`
3. In the app Setup tab, click **Import NFL Odds**
4. Player props require a paid tier and an event ID:
   - `GET /api/integrations/odds/events` lists NFL events
   - `POST /api/integrations/odds/props/import` with `{ "event_id": "..." }`

DraftKings, FanDuel, and Caesars lines are aggregated through The Odds API bookmakers. There is no separate public fantasy API key for those brands.

## Sleeper (league data and projections)

- **League/players:** public API, no key required. Use Setup → Import League.
- **Projections:** unofficial endpoint `https://api.sleeper.app/projections/nfl/{season}/{week}`. Use Setup → **Import Sleeper Projections**.

## ESPN fantasy rankings

ESPN does not provide a stable public fantasy API key (`ESPN_API_KEY` is a placeholder only).

Import rankings manually:

1. Export or build a JSON array of ranking rows
2. Setup → Rankings JSON
3. Set **source name** to `espn`
4. Click **Import Rankings JSON**

Example row:

```json
{
  "player_name": "Ja'Marr Chase",
  "team": "CIN",
  "position": "WR",
  "overall_rank": 5,
  "adp": 6.2,
  "projected_points": 300
}
```

## Personal draft style

- **Favorites:** star players in the mock draft pick sheet
- **Reach/value bias:** Setup → Favorites and Draft Style
- **Tendencies:** **Calculate My Tendencies** uses your imported Sleeper pick history
