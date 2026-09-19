"""Tiny JSON-over-HTTP helper (stdlib only) shared by REST-based providers."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Callable

from ros2_ai_debugger.providers.base import ProviderError

HttpPost = Callable[[str, dict, dict, float], dict]


def post_json(url: str, body: dict, headers: dict, timeout: float) -> dict:
    """POST JSON, return decoded JSON. Errors never echo request headers (API keys)."""
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(), method="POST",
        headers={"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:300]
        raise ProviderError(f"HTTP {exc.code} from {url.split('?')[0]}: {detail}") from None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ProviderError(f"could not reach {url.split('?')[0]}: {getattr(exc, 'reason', exc)}") from None
    except json.JSONDecodeError:
        raise ProviderError(f"{url.split('?')[0]} returned a non-JSON response") from None


def get_json(url: str, timeout: float) -> dict:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return json.loads(resp.read())
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise ProviderError(f"could not query {url}: {getattr(exc, 'reason', exc)}") from None
