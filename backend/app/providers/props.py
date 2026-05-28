"""Props provider adapter placeholder.

The Odds API supports player prop markets through event-level odds endpoints on
plans that include those markets. This MVP keeps the direct pull as a future
adapter and supports JSON imports now.
"""

from .provider_stub import ConfiguredProvider


class PropsClient(ConfiguredProvider):
    source_name = "props"
    env_var = "ODDS_API_KEY"
    message = "Props API is not configured. Set ODDS_API_KEY for an approved odds provider or use player props JSON import."
