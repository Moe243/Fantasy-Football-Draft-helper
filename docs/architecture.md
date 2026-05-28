# Architecture Notes

## Core Principle

Keep the fantasy logic deterministic and inspectable. The chatbot should explain and retrieve recommendations from the engine; it should not be the source of truth for rankings, player availability, or league state.

## Provider Layer

Each external source should land in a provider adapter:

- `SleeperClient`: league settings, rosters, users, drafts, draft picks, players, trending adds/drops.
- `OddsClient`: game odds, totals, spreads, and market movement.
- Future `ProjectionClient`: seasonal and weekly projections.
- Future `UsageClient`: snaps, routes, targets, carries, red-zone work.
- Future `NewsClient`: injuries, beat reports, official inactive lists.

Adapters should write raw snapshots first, then a normalization job should update canonical tables. That keeps debugging sane when a source changes shape.

## Recommendation Engine

Draft score blends:

- projected value above replacement,
- ADP value,
- roster need,
- positional scarcity,
- usage and trend signals,
- injury/status penalty,
- betting context.

Waiver score blends:

- recent trend score,
- snaps/routes/targets/carries,
- depth-chart opportunity,
- injury-created role changes,
- rostered percentage,
- matchup and market movement.

## Chat Layer

The current chat route is a rule-based intent router. A production LLM layer should expose internal tools:

- `get_draft_recommendations`
- `get_waiver_risers`
- `evaluate_keeper`
- `get_matchup_edges`
- `explain_player`

The model can write the conversational answer, but tool results should carry the data and rankings.
