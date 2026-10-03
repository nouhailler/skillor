from datetime import date, datetime
from pydantic import BaseModel, ConfigDict

class OccupationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str; canonical_name: str; description: str | None = None; sector: str | None = None; esco_uri: str | None = None

class SkillOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str; canonical_name: str; description: str | None = None; skill_type: str | None = None; esco_uri: str | None = None

class ImportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str; status: str; started_at: datetime; finished_at: datetime | None; records_fetched: int; records_stored: int; error: str | None

class TrendOut(BaseModel):
    entity_id: str; name: str; score: float; growth: float; period: date; method_version: str; is_official: bool
