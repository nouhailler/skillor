from app.config import settings
from app.connectors.base import BaseConnector

class EscoConnector(BaseConnector):
    slug = "esco"
    base_url = settings.esco_base_url.rstrip("/")

    async def _fetch_resources(self, kind: str, uris: list[str], language: str) -> dict[str, dict]:
        resources: dict[str, dict] = {}
        batch_size = max(1, min(settings.esco_batch_size, 50))
        for start in range(0, len(uris), batch_size):
            batch = uris[start:start + batch_size]
            params = [("uris", uri) for uri in batch]
            params.extend((("language", language), ("selectedVersion", settings.esco_version)))
            payload = await self.request_json("GET", f"{self.base_url}/resource/{kind}", params=params)
            embedded = payload.get("_embedded", {})
            for key, value in embedded.items():
                if isinstance(value, dict) and value.get("uri"):
                    resources[value["uri"]] = value
                elif isinstance(value, list):
                    for item in value:
                        if isinstance(item, dict) and item.get("uri"):
                            resources[item["uri"]] = item
            if payload.get("uri"):
                resources[payload["uri"]] = payload
        return resources

    async def fetch(self, query: str = "data", limit: int = 50, language: str | None = None, include_relations: bool = True, max_relation_skills: int | None = None, **_) -> dict:
        language = language or settings.esco_language
        results: dict[str, dict] = {}
        for kind in ("occupation", "skill"):
            results[kind] = await self.request_json("GET", f"{self.base_url}/search", params={"text": query, "type": kind, "language": language, "limit": min(limit, 100), "selectedVersion": settings.esco_version})
        occupation_uris = [item.get("uri") for item in self._items(results["occupation"]) if item.get("uri")]
        skill_uris = [item.get("uri") for item in self._items(results["skill"]) if item.get("uri")]
        occupation_details = await self._fetch_resources("occupation", occupation_uris, language)
        if include_relations:
            for detail in occupation_details.values():
                links = detail.get("_links", {})
                for key in ("hasEssentialSkill", "hasOptionalSkill"):
                    skill_uris.extend(item.get("uri") for item in links.get(key, []) if item.get("uri"))
        unique_skill_uris = list(dict.fromkeys(skill_uris))
        maximum = max_relation_skills if max_relation_skills is not None else settings.esco_max_relation_skills
        skill_details = await self._fetch_resources("skill", unique_skill_uris[:maximum], language)
        return {"query": query, "language": language, "selected_version": settings.esco_version, "results": results, "occupation_details": occupation_details, "skill_details": skill_details, "truncated_skill_details": max(0, len(unique_skill_uris) - maximum)}

    @staticmethod
    def _items(payload: dict) -> list[dict]:
        embedded = payload.get("_embedded", {})
        for key in ("results", "concepts", "occupations", "skills"):
            if isinstance(embedded.get(key), list):
                return embedded[key]
        return payload.get("results", []) if isinstance(payload.get("results"), list) else []

    @staticmethod
    def _text_map(value: object) -> dict[str, str]:
        if not isinstance(value, dict):
            return {}
        result = {}
        for language, content in value.items():
            if isinstance(content, str):
                result[language] = content
            elif isinstance(content, dict) and content.get("literal"):
                result[language] = content["literal"]
        return result

    @staticmethod
    def _aliases(value: object) -> dict[str, list[str]]:
        if not isinstance(value, dict):
            return {}
        aliases = {}
        for language, labels in value.items():
            if isinstance(labels, list):
                aliases[language] = list(dict.fromkeys(label for label in labels if isinstance(label, str)))
            elif isinstance(labels, str):
                aliases[language] = [labels]
        return aliases

    @staticmethod
    def _skill_type(item: dict) -> str | None:
        value = item.get("skillType") or item.get("skill_type")
        return value.rsplit("/", 1)[-1] if isinstance(value, str) else value

    @staticmethod
    def _isco_code(item: dict) -> str | None:
        groups = item.get("_links", {}).get("broaderIscoGroup", [])
        if groups:
            return groups[0].get("code") or groups[0].get("uri", "").rsplit("C", 1)[-1] or None
        return None

    def _entity(self, kind: str, item: dict, language: str) -> dict | None:
        uri = item.get("uri") or item.get("conceptUri")
        labels = self._text_map(item.get("preferredLabel") or item.get("prefLabel"))
        descriptions = self._text_map(item.get("description"))
        title = item.get("title") or labels.get(language) or labels.get("en") or next(iter(labels.values()), None)
        if not uri or not title:
            return None
        return {"entity_type": kind, "canonical_name": title, "description": descriptions.get(language) or descriptions.get("en"), "esco_uri": uri, "aliases": self._aliases(item.get("alternativeLabel") or item.get("altLabels")), "multilingual_labels": labels, "multilingual_descriptions": descriptions, "isco_code": self._isco_code(item) if kind == "occupation" else None, "skill_type": self._skill_type(item) if kind == "skill" else None, "raw": item}

    def normalize(self, payload: dict) -> dict[str, list[dict]]:
        language = payload.get("language", "fr")
        entities: dict[str, dict] = {}
        occupation_details = payload.get("occupation_details", {})
        skill_details = payload.get("skill_details", {})
        for kind, group in payload.get("results", {}).items():
            details = occupation_details if kind == "occupation" else skill_details
            for item in self._items(group):
                detail = details.get(item.get("uri"), item)
                entity = self._entity(kind, detail, language)
                if entity:
                    entities[entity["esco_uri"]] = entity
        relations = []
        for occupation_uri, occupation in occupation_details.items():
            entity = self._entity("occupation", occupation, language)
            if entity:
                entities[occupation_uri] = entity
            links = occupation.get("_links", {})
            for relationship_type, key, weight in (("essential", "hasEssentialSkill", 1.0), ("optional", "hasOptionalSkill", 0.6)):
                for link in links.get(key, []):
                    skill_uri = link.get("uri")
                    if not skill_uri:
                        continue
                    skill_item = skill_details.get(skill_uri, link)
                    skill = self._entity("skill", skill_item, language)
                    if skill:
                        entities[skill_uri] = skill
                    relations.append({"occupation_uri": occupation_uri, "skill_uri": skill_uri, "relationship_type": relationship_type, "weight": weight})
        for skill_uri, item in skill_details.items():
            entity = self._entity("skill", item, language)
            if entity:
                entities[skill_uri] = entity
        return {"entities": list(entities.values()), "relations": relations}
