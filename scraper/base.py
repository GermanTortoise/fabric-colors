import random
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Iterable

import requests
from bs4 import BeautifulSoup


@dataclass
class FabricRecord:
    store_product_id: str
    name: str
    url: str
    image_url: str | None = None
    raw_color_name: str | None = None
    material: str | None = None
    weave: str | None = None
    weight_gsm: float | None = None
    width_inches: float | None = None
    content: str | None = None


class BaseScraper(ABC):
    slug: str = ""
    name: str = ""
    base_url: str = ""
    crawl_delay: float = 10.0
    user_agent: str = "fabric-colors-bot/0.1 (+contact@example.com)"

    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers["User-Agent"] = self.user_agent

    def fetch(self, url: str) -> str:
        time.sleep(self.crawl_delay + random.uniform(0, 2))
        resp = self.session.get(url, timeout=30)
        resp.raise_for_status()
        return resp.text

    def soup(self, html: str) -> BeautifulSoup:
        return BeautifulSoup(html, "html.parser")

    @abstractmethod
    def iter_records(self) -> Iterable[FabricRecord]:
        """Yield FabricRecord instances. The scraper handles discovery + parsing."""

    def is_solid(self, record: FabricRecord) -> bool:
        name = record.name.lower()
        patterned = (
            "print", "floral", "stripe", "plaid", "check", "pattern",
            "polka", "dot", "geometric", "paisley", "tartan", "houndstooth",
        )
        return not any(p in name for p in patterned)
