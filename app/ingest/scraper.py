from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class Scraper:
    user_agent: str = "nauda-palisse-veille/0.1"
    timeout: float = 10.0

    def run(self, urls: list[str]) -> list[dict[str, Any]]:
        raise NotImplementedError
