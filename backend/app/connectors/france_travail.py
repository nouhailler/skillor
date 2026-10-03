from app.config import settings
from app.connectors.base import BaseConnector, CredentialsRequired

class FranceTravailConnector(BaseConnector):
    slug = "france_travail"
    base_url = settings.france_travail_base_url.rstrip("/")

    async def _token(self) -> str:
        if not settings.france_travail_client_id or not settings.france_travail_client_secret:
            raise CredentialsRequired("Les identifiants OAuth France Travail sont requis")
        payload = await self.request_json("POST", settings.france_travail_token_url, data={"grant_type": "client_credentials", "client_id": settings.france_travail_client_id, "client_secret": settings.france_travail_client_secret, "scope": settings.france_travail_scope}, headers={"Content-Type": "application/x-www-form-urlencoded"})
        return payload["access_token"]

    async def fetch(self, endpoint: str = "indicateurs", territory: str = "FR", **_) -> dict:
        token = await self._token()
        return await self.request_json("GET", f"{self.base_url}/{endpoint.lstrip('/')}", params={"territoire": territory}, headers={"Authorization": f"Bearer {token}", "Accept": "application/json"})

    def normalize(self, payload: dict) -> list[dict]:
        rows = payload.get("resultats") or payload.get("results") or payload.get("items") or []
        normalized = []
        for row in rows:
            metric = row.get("indicateur") or row.get("metric") or row.get("type")
            value = row.get("valeur") if "valeur" in row else row.get("value")
            if metric and value is not None:
                normalized.append({"metric": str(metric), "value": float(value), "unit": row.get("unite") or row.get("unit") or "count", "period": row.get("periode") or row.get("period"), "geography_code": row.get("territoire") or row.get("geo") or "FR", "raw": row})
        return normalized
