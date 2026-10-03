import itertools
from app.config import settings
from app.connectors.base import BaseConnector
from app.eurostat_catalog import eurostat_catalog

class EurostatConnector(BaseConnector):
    slug = "eurostat"
    base_url = settings.eurostat_base_url.rstrip("/")

    async def fetch(self, profile: str | None = None, dataset: str | None = None, geography: str = "FR",
                    since: int = 2021, filters: dict | None = None, **_) -> dict:
        catalog = eurostat_catalog()
        spec = catalog.get(profile or "")
        dataset_code = dataset or (spec or {}).get("code") or settings.eurostat_dataset
        applied_filters = {**(spec or {}).get("filters", {}), **(filters or {})}
        params = [("lang", "FR"), ("sinceTimePeriod", str(since))]
        if (spec or {}).get("geography_level") != "nuts2" and geography:
            params.append(("geo", geography))
        for key, value in applied_filters.items():
            values = value if isinstance(value, list) else [value]
            params.extend((key, str(item)) for item in values)
        payload = await self.request_json("GET", f"{self.base_url}/{dataset_code}", params=params)
        payload["_skillor_dataset"] = dataset_code
        payload["_skillor_profile"] = profile or dataset_code
        payload["_skillor_metric"] = (spec or {}).get("metric", dataset_code.lower())
        payload["_skillor_family"] = (spec or {}).get("family", "custom")
        payload["_skillor_output_unit"] = (spec or {}).get("output_unit")
        payload["_skillor_geography_level"] = (spec or {}).get("geography_level", "country")
        payload["_skillor_geography_prefix"] = (spec or {}).get("geography_prefix")
        payload["_skillor_filters"] = applied_filters
        return payload

    @staticmethod
    def _ordered_codes(dimension: dict) -> list[str]:
        index = dimension.get("category", {}).get("index", {})
        if isinstance(index, list):
            return index
        return [code for code, _ in sorted(index.items(), key=lambda pair: pair[1])]

    def normalize(self, payload: dict) -> list[dict]:
        dataset_code = payload.get("_skillor_dataset", settings.eurostat_dataset)
        inferred_profile, inferred_spec = next(((name, spec) for name, spec in eurostat_catalog().items() if spec["code"] == dataset_code), (dataset_code, {}))
        metric = payload.get("_skillor_metric") or inferred_spec.get("metric") or dataset_code.lower()
        family = payload.get("_skillor_family") or inferred_spec.get("family", "custom")
        geography_level = payload.get("_skillor_geography_level") or inferred_spec.get("geography_level", "country")
        ids, sizes = payload.get("id", []), payload.get("size", [])
        dimensions = [self._ordered_codes(payload["dimension"][dim]) for dim in ids]
        values = payload.get("value", {})
        statuses = payload.get("status", {})
        geography_labels = payload.get("dimension", {}).get("geo", {}).get("category", {}).get("label", {})
        dimension_labels = {
            dim: payload.get("dimension", {}).get(dim, {}).get("category", {}).get("label", {})
            for dim in ids
        }
        records = []
        for flat_index, coordinates in enumerate(itertools.product(*dimensions)):
            value = values.get(str(flat_index)) if isinstance(values, dict) else (values[flat_index] if flat_index < len(values) else None)
            if value is None:
                continue
            point = dict(zip(ids, coordinates))
            geography_code = point.get("geo", "FR")
            prefix = payload.get("_skillor_geography_prefix") or inferred_spec.get("geography_prefix")
            if prefix and not geography_code.startswith(prefix):
                continue
            status = statuses.get(str(flat_index)) if isinstance(statuses, dict) else (statuses[flat_index] if flat_index < len(statuses) else None)
            labels = {dim: dimension_labels[dim].get(code, code) for dim, code in point.items()}
            records.append({
                "metric": metric,
                "value": float(value), "unit": payload.get("_skillor_output_unit") or point.get("unit", "value"), "period": point.get("time"),
                "geography_code": geography_code, "geography_name": geography_labels.get(geography_code, geography_code),
                "geography_level": geography_level,
                "dimensions": point, "dimension_labels": labels, "status": status,
                "dataset": dataset_code,
                "profile": payload.get("_skillor_profile") or inferred_profile, "family": family,
                "updated": payload.get("updated"),
            })
        return records
