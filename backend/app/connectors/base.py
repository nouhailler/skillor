import asyncio
import json
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
import httpx
from app.config import settings

class ConnectorError(RuntimeError):
    pass

class CredentialsRequired(ConnectorError):
    pass

class BaseConnector(ABC):
    slug: str
    base_url: str

    def __init__(self, client: httpx.AsyncClient | None = None):
        self.client = client or httpx.AsyncClient(timeout=httpx.Timeout(30, connect=10), follow_redirects=True)
        self._owns_client = client is None

    async def close(self):
        if self._owns_client:
            await self.client.aclose()

    async def request_json(self, method: str, url: str, **kwargs) -> dict:
        error = None
        for attempt in range(4):
            try:
                response = await self.client.request(method, url, **kwargs)
                response.raise_for_status()
                return response.json()
            except (httpx.HTTPError, ValueError) as exc:
                error = exc
                if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code < 500 and exc.response.status_code != 429:
                    break
                await asyncio.sleep(0.4 * 2**attempt)
        raise ConnectorError(f"{self.slug}: {error}") from error

    def store_raw(self, payload: dict, suffix: str = "response") -> str:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        directory = Path(settings.raw_data_dir) / self.slug / stamp[:8]
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / f"{stamp}-{suffix}.json"
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return str(target)

    @abstractmethod
    async def fetch(self, **kwargs) -> dict: ...

    @abstractmethod
    def normalize(self, payload: dict) -> list[dict]: ...
