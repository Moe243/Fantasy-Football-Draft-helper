"""Small urllib helper so the MVP has no third-party dependency."""

from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class ProviderError(RuntimeError):
    pass


def get_json(url: str, params: dict[str, Any] | None = None, timeout: int = 12) -> Any:
    if params:
        url = f"{url}?{urlencode(params)}"
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "fantasy-football-assistant/0.1"})
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise ProviderError(f"{exc.code} from {url}: {body[:300]}") from exc
    except URLError as exc:
        raise ProviderError(f"Could not reach {url}: {exc.reason}") from exc
