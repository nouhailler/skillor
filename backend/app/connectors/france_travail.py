import re
import unicodedata
from collections import defaultdict
from datetime import date
from typing import Any

from app.config import settings
from app.connectors.base import BaseConnector, CredentialsRequired

METRIC_ALIASES = {
    "offres": "job_offers", "offres_emploi": "job_offers", "job_offers": "job_offers",
    "demandeurs": "job_seekers", "demandeurs_emploi": "job_seekers", "job_seekers": "job_seekers",
    "embauches": "hires", "recrutements": "hires", "hires": "hires",
    "difficulte_recrutement": "recruitment_difficulty",
    "difficultes_recrutement": "recruitment_difficulty",
    "tension": "recruitment_difficulty",
    "salaire": "salary_average", "salaire_moyen": "salary_average",
}

def _first(row: dict, *paths: str, default=None):
    for path in paths:
        value: Any = row
        for part in path.split("."):
            if not isinstance(value, dict) or part not in value:
                value = None
                break
            value = value[part]
        if value not in (None, ""):
            return value
    return default

def _metric(value: object) -> str:
    ascii_value = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode()
    key = re.sub(r"[^a-z0-9]+", "_", ascii_value.lower()).strip("_")
    return METRIC_ALIASES.get(key, key)

class FranceTravailConnector(BaseConnector):
    slug = "france_travail"
    base_url = settings.france_travail_base_url.rstrip("/")

    async def _token(self, scope: str | None = None) -> str:
        if not settings.france_travail_client_id or not settings.france_travail_client_secret:
            raise CredentialsRequired("Les identifiants OAuth France Travail sont requis")
        payload = await self.request_json(
            "POST", settings.france_travail_token_url,
            data={"grant_type": "client_credentials", "client_id": settings.france_travail_client_id,
                  "client_secret": settings.france_travail_client_secret, "scope": scope or settings.france_travail_scope},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        return payload["access_token"]

    async def fetch(self, dataset: str = "market", endpoint: str = "indicateurs", territory: str = "FR",
                    query: str | None = None, rome_code: str | None = None, limit: int = 150, **_) -> dict:
        if dataset == "offers":
            token = await self._token(settings.france_travail_offers_scope)
            params: dict[str, str] = {"range": f"0-{max(0, min(limit, 150) - 1)}"}
            if territory and territory != "FR": params["departement"] = territory
            if query: params["motsCles"] = query
            if rome_code: params["romeProfessionCardCode"] = rome_code
            payload = await self.request_json("GET", settings.france_travail_offers_url, params=params,
                                              headers={"Authorization": f"Bearer {token}", "Accept": "application/json"})
            payload["_skillor_dataset"] = "france_travail_offers_v2"
            payload["_skillor_kind"] = "offers"
            return payload
        token = await self._token()
        payload = await self.request_json("GET", f"{self.base_url}/{endpoint.lstrip('/')}",
                                          params={"territoire": territory},
                                          headers={"Authorization": f"Bearer {token}", "Accept": "application/json"})
        payload["_skillor_dataset"] = f"france_travail_{endpoint.replace('/', '_')}"
        payload["_skillor_kind"] = "market"
        return payload

    @staticmethod
    def _context(row: dict) -> dict:
        flat_territory = row.get("territoire") if isinstance(row.get("territoire"), str) else None
        geography_code = _first(row, "geography_code", "geo", "codeTerritoire", "territoire.code",
                                "lieuTravail.commune", "lieuTravail.codePostal", default=flat_territory or "FR")
        geography_name = _first(row, "geography_name", "libelleTerritoire", "territoire.libelle",
                                "lieuTravail.libelle", default="France" if geography_code == "FR" else str(geography_code))
        geography_code = str(geography_code)
        geography_level = _first(row, "geography_level", "niveauTerritoire", "territoire.niveau")
        if not geography_level:
            geography_level = "country" if geography_code == "FR" else "commune" if geography_code.isdigit() and len(geography_code) == 5 else "department"
        return {
            "occupation_external_scheme": "rome_v4",
            "occupation_external_code": _first(row, "romeCode", "codeRome", "code_rome", "metier.codeRome", "metier.code"),
            "occupation_label": _first(row, "romeLibelle", "libelleRome", "metier.libelle", "appellationlibelle", "intitule"),
            "occupation_appellation_label": _first(row, "appellationlibelle", "appellation.libelle"),
            "esco_uri": _first(row, "escoUri", "esco_uri", "metier.escoUri"),
            "isco_code": _first(row, "iscoCode", "isco_code", "metier.iscoCode"),
            "geography_code": geography_code, "geography_name": str(geography_name),
            "geography_level": str(geography_level).lower(),
            "sector_code": _first(row, "secteurActivite", "secteur.code", "naf"),
            "sector_name": _first(row, "secteurActiviteLibelle", "secteur.libelle"),
        }

    def _normalize_indicators(self, rows: list[dict]) -> list[dict]:
        normalized = []
        for row in rows:
            metric = _first(row, "indicateur", "metric", "type", "codeIndicateur")
            value = _first(row, "valeur", "value", "nombre", "taux")
            if metric is None or value is None: continue
            context = self._context(row)
            normalized.append({
                "metric": _metric(metric), "value": float(str(value).replace(",", ".")),
                "unit": _first(row, "unite", "unit", default="count"),
                "period": _first(row, "periode", "period", "date", default=date.today().isoformat()),
                **context,
                "dimensions": {"sector_code": context["sector_code"], "sector_name": context["sector_name"],
                               "category": _first(row, "categorie", "category")},
                "raw": row,
            })
        return normalized

    @staticmethod
    def _salary(row: dict) -> list[tuple[str, float, str]]:
        salary = row.get("salaire") or row.get("salary") or {}
        if not isinstance(salary, dict): salary = {"libelle": str(salary)}
        unit = _first(salary, "unite", "unit", "periode", default="unspecified")
        values = []
        for metric, keys in {"salary_min": ("min", "minimum", "valeurMin"),
                             "salary_max": ("max", "maximum", "valeurMax"),
                             "salary_average": ("moyen", "average", "valeur")}.items():
            value = _first(salary, *keys)
            if value is not None:
                try: values.append((metric, float(str(value).replace(",", ".")), str(unit)))
                except ValueError: pass
        if not values and salary.get("libelle"):
            label = unicodedata.normalize("NFKD", str(salary["libelle"])).encode("ascii", "ignore").decode().lower()
            unit = "EUR/hour" if "horaire" in label else "EUR/month" if "mensuel" in label else "EUR/year" if "annuel" in label else "EUR"
            segment = label.split(" sur ", 1)[0]
            amounts = [float(value.replace(" ", "").replace(",", ".")) for value in re.findall(r"\d[\d ]*(?:[.,]\d+)?", segment)]
            if amounts:
                values.append(("salary_min", amounts[0], unit))
                values.append(("salary_max", amounts[1] if len(amounts) > 1 else amounts[0], unit))
        return values

    def _normalize_offers(self, rows: list[dict]) -> list[dict]:
        counts: defaultdict[tuple, int] = defaultdict(int)
        contexts: dict[tuple, dict] = {}
        skills: defaultdict[tuple, int] = defaultdict(int)
        salaries: defaultdict[tuple, list[float]] = defaultdict(list)
        for row in rows:
            context = self._context(row)
            raw_period = str(_first(row, "dateCreation", "dateActualisation", default=date.today().isoformat()))
            period = raw_period[:7] + "-01" if len(raw_period) >= 7 else raw_period
            key = (context["occupation_external_code"], context["occupation_label"],
                   context["occupation_appellation_label"], context["geography_code"], context["sector_code"], period)
            counts[key] += 1; contexts[key] = context
            for skill in row.get("competences") or row.get("skills") or []:
                if not isinstance(skill, dict): skill = {"libelle": skill}
                label = _first(skill, "libelle", "label", "nom")
                if label: skills[key + (str(_first(skill, "code", "id", default="")), str(label))] += 1
            for metric, value, unit in self._salary(row): salaries[key + (metric, unit)].append(value)
        normalized = []
        for key, count in counts.items():
            context = contexts[key]
            normalized.append({"metric": "job_offers", "value": float(count), "unit": "offer", "period": key[-1],
                               **context, "dimensions": {"sector_code": context["sector_code"], "sector_name": context["sector_name"]}})
        for key, count in skills.items():
            base, skill_code, skill_label = key[:-2], key[-2], key[-1]; context = contexts[base]
            normalized.append({"metric": "skill_offer_mentions", "value": float(count), "unit": "mention", "period": base[-1],
                               **context, "skill_external_code": skill_code or None, "skill_label": skill_label,
                               "dimensions": {"sector_code": context["sector_code"], "sector_name": context["sector_name"]}})
        for key, values in salaries.items():
            base, metric, unit = key[:-2], key[-2], key[-1]; context = contexts[base]
            normalized.append({"metric": metric, "value": sum(values) / len(values), "unit": unit, "period": base[-1],
                               **context, "dimensions": {"sample_size": len(values), "sector_code": context["sector_code"],
                                                          "sector_name": context["sector_name"]}})
        return normalized

    def normalize(self, payload: dict) -> list[dict]:
        rows = payload.get("resultats") or payload.get("results") or payload.get("items") or []
        if payload.get("_skillor_kind") == "offers" or any("romeCode" in row or "intitule" in row for row in rows):
            return self._normalize_offers(rows)
        return self._normalize_indicators(rows)
