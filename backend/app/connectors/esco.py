from app.config import settings
from app.connectors.base import BaseConnector

class EscoConnector(BaseConnector):
    slug = "esco"
    base_url = settings.esco_base_url.rstrip("/")

    async def fetch(self, query: str = "data", limit: int = 50, language: str | None = None) -> dict:
        language = language or settings.esco_language
        results: dict[str, dict] = {}
        for kind in ("occupation", "skill"):
            results[kind] = await self.request_json("GET", f"{self.base_url}/search", params={"text": query, "type": kind, "language": language, "limit": min(limit, 100), "selectedVersion": settings.esco_version})
        return {"query": query, "language": language, "results": results}

    @staticmethod
    def _items(payload: dict) -> list[dict]:
        embedded = payload.get("_embedded", {})
        for key in ("results", "concepts", "occupations", "skills"):
            if isinstance(embedded.get(key), list):
                return embedded[key]
        return payload.get("results", []) if isinstance(payload.get("results"), list) else []

    def normalize(self, payload: dict) -> list[dict]:
        normalized = []
        for kind, group in payload.get("results", {}).items():
            for item in self._items(group):
                title = item.get("title") or item.get("preferredLabel") or item.get("prefLabel")
                if isinstance(title, dict):
                    title = title.get(payload.get("language", "fr")) or next(iter(title.values()), None)
                uri = item.get("uri") or item.get("conceptUri") or item.get("_links", {}).get("self", {}).get("href")
                if title and uri:
                    normalized.append({"entity_type": kind, "canonical_name": title, "description": item.get("description"), "esco_uri": uri, "aliases": item.get("alternativeLabel") or item.get("altLabels") or [], "raw": item})
        return normalized
