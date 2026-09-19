"""Terminal capability helpers."""
from __future__ import annotations

import os
from typing import TextIO


def supports_color(stream: TextIO, force_off: bool = False) -> bool:
    """Colors only on a real TTY, honoring NO_COLOR (https://no-color.org) and TERM=dumb."""
    if force_off or "NO_COLOR" in os.environ or os.environ.get("TERM") == "dumb":
        return False
    return bool(getattr(stream, "isatty", lambda: False)())


def supports_unicode(stream: TextIO) -> bool:
    return "utf" in (getattr(stream, "encoding", None) or "").lower()
