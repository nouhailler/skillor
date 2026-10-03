import json
from copy import deepcopy

from app.config import settings

DEFAULT_EUROSTAT_CATALOG = {
    "unemployment": {
        "code": "une_rt_a", "name": "Taux de chômage", "family": "unemployment",
        "metric": "unemployment_rate", "geography_level": "country",
        "filters": {"sex": "T", "age": "Y15-74", "unit": "PC_ACT"},
    },
    "employment": {
        "code": "lfsi_emp_a", "name": "Taux d'emploi", "family": "employment",
        "metric": "employment_rate", "geography_level": "country",
        "filters": {"indic_em": "EMP_LFS", "sex": "T", "age": "Y20-64", "unit": "PC_POP"},
    },
    "wages": {
        "code": "earn_ses_monthly", "name": "Rémunération mensuelle moyenne", "family": "wages",
        "metric": "mean_monthly_earnings", "output_unit": "EUR/month", "geography_level": "country",
        "filters": {"nace_r2": "B-S_X_O", "isco08": "TOTAL", "worktime": "TOTAL", "age": "TOTAL",
                    "sex": "T", "indic_se": "MEAN_E_EUR"},
    },
    "education": {
        "code": "edat_lfse_03", "name": "Niveau d'éducation de la population", "family": "education",
        "metric": "education_attainment_share", "geography_level": "country",
        "filters": {"sex": "T", "age": "Y25-64", "unit": "PC"},
    },
    "sectors": {
        "code": "lfsa_egan2", "name": "Emploi par secteur NACE", "family": "sectors",
        "metric": "employment_by_sector", "geography_level": "country",
        "filters": {"unit": "THS_PER", "sex": "T", "age": "Y15-74"},
    },
    "regional_unemployment": {
        "code": "lfst_r_lfu3rt", "name": "Taux de chômage régional NUTS 2", "family": "regional",
        "metric": "regional_unemployment_rate", "geography_level": "nuts2", "geography_prefix": "FR",
        "filters": {"isced11": "TOTAL", "sex": "T", "age": "Y15-74", "unit": "PC", "geoLevel": "nuts2"},
    },
}

def eurostat_catalog() -> dict[str, dict]:
    catalog = deepcopy(DEFAULT_EUROSTAT_CATALOG)
    if settings.eurostat_datasets_json:
        overrides = json.loads(settings.eurostat_datasets_json)
        for profile, values in overrides.items():
            catalog[profile] = {**catalog.get(profile, {}), **values}
    return catalog

def eurostat_profiles(value: str | list[str] | None = None) -> list[str]:
    catalog = eurostat_catalog()
    if not value or value == "all": return list(catalog)
    requested = value if isinstance(value, list) else [item.strip() for item in value.split(",") if item.strip()]
    unknown = [profile for profile in requested if profile not in catalog]
    if unknown: raise ValueError(f"Profils Eurostat inconnus: {', '.join(unknown)}")
    return requested
