import itertools
from app.config import settings
from app.connectors.base import BaseConnector

class EurostatConnector(BaseConnector):
    slug = "eurostat"
    base_url = settings.eurostat_base_url.rstrip("/")

    async def fetch(self, dataset: str | None = None, geography: str = "FR", since: int = 2021, **_) -> dict:
        dataset = dataset or settings.eurostat_dataset
        params = [("lang", "FR"), ("geo", geography), ("sinceTimePeriod", str(since)), ("sex", "T"), ("age", "Y15-74"), ("unit", "PC_ACT")]
        payload = await self.request_json("GET", f"{self.base_url}/{dataset}", params=params)
        payload["_skillor_dataset"] = dataset
        return payload

    @staticmethod
    def _ordered_codes(dimension: dict) -> list[str]:
        index = dimension.get("category", {}).get("index", {})
        if isinstance(index, list):
            return index
        return [code for code, _ in sorted(index.items(), key=lambda pair: pair[1])]

    def normalize(self, payload: dict) -> list[dict]:
        ids, sizes = payload.get("id", []), payload.get("size", [])
        dimensions = [self._ordered_codes(payload["dimension"][dim]) for dim in ids]
        values = payload.get("value", {})
        records = []
        for flat_index, coordinates in enumerate(itertools.product(*dimensions)):
            value = values.get(str(flat_index)) if isinstance(values, dict) else (values[flat_index] if flat_index < len(values) else None)
            if value is None:
                continue
            point = dict(zip(ids, coordinates))
            records.append({"metric": "unemployment_rate", "value": float(value), "unit": point.get("unit", "PC_ACT"), "period": point.get("time"), "geography_code": point.get("geo", "FR"), "dimensions": point, "dataset": payload.get("_skillor_dataset", settings.eurostat_dataset), "updated": payload.get("updated")})
        return records
