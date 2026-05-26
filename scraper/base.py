import random
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Iterable

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
    image_delay: float = 0.2
    max_retries: int = 3
    user_agent: str = "fabric-colors-bot/0.1 (+luo.yunh@northeastern.edu)"

    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers["User-Agent"] = self.user_agent

    def _request(self, url: str, timeout: int = 30) -> requests.Response:
        """GET with retry on transient errors (timeouts, connection errors, 429, 5xx).

        Backoff is exponential (1s, 2s, 4s). Honors a Retry-After header when present.
        """
        for attempt in range(self.max_retries + 1):
            try:
                resp = self.session.get(url, timeout=timeout)
            except (requests.Timeout, requests.ConnectionError) as exc:
                if attempt >= self.max_retries:
                    raise
                delay = 2 ** attempt
                print(f"  network error ({exc.__class__.__name__}); retry in {delay}s")
                time.sleep(delay)
                continue

            transient = resp.status_code == 429 or 500 <= resp.status_code < 600
            if transient and attempt < self.max_retries:
                delay = 2 ** attempt
                retry_after = resp.headers.get("Retry-After")
                if retry_after and retry_after.isdigit():
                    delay = max(delay, int(retry_after))
                print(f"  HTTP {resp.status_code} for {url}; retry in {delay}s")
                time.sleep(delay)
                continue

            resp.raise_for_status()
            return resp
        raise RuntimeError("unreachable")

    def fetch(self, url: str) -> str:
        time.sleep(self.crawl_delay + random.uniform(0, 2))
        return self._request(url).text

    def fetch_json(self, url: str) -> Any:
        time.sleep(self.crawl_delay + random.uniform(0, 2))
        return self._request(url).json()

    def fetch_image(self, url: str) -> bytes:
        time.sleep(self.image_delay)
        return self._request(url).content

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
