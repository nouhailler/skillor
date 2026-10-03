from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    app_env: str = "development"
    database_url: str = "sqlite:///./skillor.sqlite3"
    app_cors_origins: str = "http://localhost:8080,http://localhost:4173,http://127.0.0.1:8080,http://127.0.0.1:4173"
    auto_create_schema: bool = True
    seed_on_start: bool = False
    raw_data_dir: str = "./data/raw"
    admin_api_key: str = "change-me"
    esco_base_url: str = "https://ec.europa.eu/esco/api"
    esco_language: str = "fr"
    esco_version: str = "latest"
    esco_batch_size: int = 40
    esco_max_relation_skills: int = 500
    eurostat_base_url: str = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data"
    eurostat_dataset: str = "une_rt_a"
    eurostat_datasets_json: str = ""
    france_travail_token_url: str = "https://entreprise.francetravail.fr/connexion/oauth2/access_token?realm=/partenaire"
    france_travail_base_url: str = "https://api.francetravail.io/partenaire/marche-travail/v1"
    france_travail_client_id: str = ""
    france_travail_client_secret: str = ""
    france_travail_scope: str = "api_marche-travailv1"
    france_travail_offers_url: str = "https://api.francetravail.io/partenaire/offresdemploi/v2/offres/search"
    france_travail_offers_scope: str = "api_offresdemploiv2 o2dsoffre"
    france_travail_crosswalk_url: str = "https://esco.ec.europa.eu/system/files/2024-10/EURESmapping_occs_FR_v1.1.csv"

    @property
    def cors_origins(self) -> list[str]:
        return [x.strip() for x in self.app_cors_origins.split(",") if x.strip()]

@lru_cache
def get_settings() -> Settings:
    return Settings()

settings = get_settings()
