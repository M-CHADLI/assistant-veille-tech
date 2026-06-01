from __future__ import annotations

from datetime import datetime
from typing import Any


async def fetch(
    topics: list[str],
    since: datetime | None = None,
) -> list[dict[str, Any]]:
    raise NotImplementedError
