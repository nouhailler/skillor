import uuid
from datetime import date, datetime, timezone
from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db import Base

def uid() -> str:
    return str(uuid.uuid4())

def now() -> datetime:
    return datetime.now(timezone.utc)

class Source(Base):
    __tablename__ = "sources"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    slug: Mapped[str] = mapped_column(String(60), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    source_type: Mapped[str] = mapped_column(String(40), default="observed")
    base_url: Mapped[str | None] = mapped_column(String(500))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    requires_credentials: Mapped[bool] = mapped_column(Boolean, default=False)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class SourceDataset(Base):
    __tablename__ = "source_datasets"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), index=True)
    external_id: Mapped[str] = mapped_column(String(200))
    name: Mapped[str] = mapped_column(String(300))
    version: Mapped[str | None] = mapped_column(String(80))
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    __table_args__ = (UniqueConstraint("source_id", "external_id"),)

class ImportJob(Base):
    __tablename__ = "import_jobs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"), index=True)
    status: Mapped[str] = mapped_column(String(30), default="running", index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    records_fetched: Mapped[int] = mapped_column(Integer, default=0)
    records_stored: Mapped[int] = mapped_column(Integer, default=0)
    raw_path: Mapped[str | None] = mapped_column(String(500))
    error: Mapped[str | None] = mapped_column(Text)
    parameters: Mapped[dict] = mapped_column(JSON, default=dict)

class Occupation(Base):
    __tablename__ = "occupations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    canonical_name: Mapped[str] = mapped_column(String(300), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    esco_uri: Mapped[str | None] = mapped_column(String(500), unique=True)
    isco_code: Mapped[str | None] = mapped_column(String(30), index=True)
    sector: Mapped[str | None] = mapped_column(String(120), index=True)
    aliases: Mapped[dict] = mapped_column(JSON, default=dict)
    multilingual_labels: Mapped[dict] = mapped_column(JSON, default=dict)
    multilingual_descriptions: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    skills: Mapped[list["OccupationSkill"]] = relationship(back_populates="occupation", cascade="all, delete-orphan")
    external_mappings: Mapped[list["ExternalOccupationMapping"]] = relationship(back_populates="occupation", cascade="all, delete-orphan")

class ExternalOccupationMapping(Base):
    __tablename__ = "external_occupation_mappings"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    occupation_id: Mapped[str] = mapped_column(ForeignKey("occupations.id", ondelete="CASCADE"), index=True)
    source_system: Mapped[str] = mapped_column(String(80), index=True)
    external_code: Mapped[str] = mapped_column(String(120), index=True)
    external_label: Mapped[str | None] = mapped_column(String(500), index=True)
    mapping_relation: Mapped[str] = mapped_column(String(80), default="exactMatch")
    mapping_method: Mapped[str] = mapped_column(String(80), default="official_crosswalk")
    confidence_score: Mapped[float] = mapped_column(Float, default=1.0)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    occupation: Mapped[Occupation] = relationship(back_populates="external_mappings")
    __table_args__ = (UniqueConstraint("occupation_id", "source_system", "external_code"),)

class SearchTerm(Base):
    __tablename__ = "search_terms"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    entity_type: Mapped[str] = mapped_column(String(30), index=True)
    entity_id: Mapped[str] = mapped_column(String(36), index=True)
    term: Mapped[str] = mapped_column(String(500))
    normalized_term: Mapped[str] = mapped_column(String(500), index=True)
    language: Mapped[str | None] = mapped_column(String(12), index=True)
    source: Mapped[str] = mapped_column(String(80), index=True)
    term_type: Mapped[str] = mapped_column(String(40), index=True)
    identifier: Mapped[str | None] = mapped_column(String(500), index=True)
    __table_args__ = (
        UniqueConstraint("entity_type", "entity_id", "normalized_term", "language", "source", "term_type", name="uq_search_term_identity"),
        Index("ix_search_terms_entity", "entity_type", "entity_id"),
    )

class Skill(Base):
    __tablename__ = "skills"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    canonical_name: Mapped[str] = mapped_column(String(300), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    esco_uri: Mapped[str | None] = mapped_column(String(500), unique=True)
    skill_type: Mapped[str | None] = mapped_column(String(80), index=True)
    aliases: Mapped[dict] = mapped_column(JSON, default=dict)
    multilingual_labels: Mapped[dict] = mapped_column(JSON, default=dict)
    multilingual_descriptions: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    occupations: Mapped[list["OccupationSkill"]] = relationship(back_populates="skill", cascade="all, delete-orphan")

class OccupationSkill(Base):
    __tablename__ = "occupation_skills"
    occupation_id: Mapped[str] = mapped_column(ForeignKey("occupations.id", ondelete="CASCADE"), primary_key=True)
    skill_id: Mapped[str] = mapped_column(ForeignKey("skills.id", ondelete="CASCADE"), primary_key=True)
    relationship_type: Mapped[str] = mapped_column(String(40), default="essential")
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    source_id: Mapped[str | None] = mapped_column(ForeignKey("sources.id"))
    confidence_score: Mapped[float] = mapped_column(Float, default=1.0)
    occupation: Mapped[Occupation] = relationship(back_populates="skills")
    skill: Mapped[Skill] = relationship(back_populates="occupations")

class Observation(Base):
    __tablename__ = "observations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    occupation_id: Mapped[str | None] = mapped_column(ForeignKey("occupations.id"), index=True)
    skill_id: Mapped[str | None] = mapped_column(ForeignKey("skills.id"), index=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"), index=True)
    dataset_id: Mapped[str | None] = mapped_column(ForeignKey("source_datasets.id"))
    metric: Mapped[str] = mapped_column(String(80), index=True)
    value: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(50))
    period: Mapped[date] = mapped_column(Date, index=True)
    geography_code: Mapped[str] = mapped_column(String(30), default="FR", index=True)
    geography_name: Mapped[str] = mapped_column(String(150), default="France")
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    natural_key: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    __table_args__ = (Index("ix_observation_lookup", "metric", "period", "geography_code"),)

class DataQualityScore(Base):
    __tablename__ = "data_quality_scores"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), index=True)
    dataset_id: Mapped[str | None] = mapped_column(ForeignKey("source_datasets.id", ondelete="CASCADE"), index=True)
    scope_key: Mapped[str] = mapped_column(String(80), default="__source__")
    metric: Mapped[str] = mapped_column(String(80), index=True)
    period: Mapped[date] = mapped_column(Date, index=True)
    score: Mapped[float] = mapped_column(Float)
    source_quality: Mapped[float] = mapped_column(Float)
    recency: Mapped[float] = mapped_column(Float)
    coverage: Mapped[float] = mapped_column(Float)
    consistency: Mapped[float] = mapped_column(Float)
    cross_source_agreement: Mapped[float] = mapped_column(Float)
    sample_size: Mapped[int] = mapped_column(Integer)
    diagnostics: Mapped[dict] = mapped_column(JSON, default=dict)
    method_version: Mapped[str] = mapped_column(String(20), default="1.0-observed")
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    is_official: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (UniqueConstraint("source_id", "scope_key", "metric", "period", "method_version"),)

class ProspectiveEdition(Base):
    __tablename__ = "prospective_editions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), index=True)
    report_title: Mapped[str] = mapped_column(String(300))
    edition: Mapped[str] = mapped_column(String(80), index=True)
    publication_year: Mapped[int] = mapped_column(Integer)
    horizon_year: Mapped[int | None] = mapped_column(Integer)
    source_url: Mapped[str | None] = mapped_column(String(500))
    raw_path: Mapped[str | None] = mapped_column(String(500))
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    __table_args__ = (UniqueConstraint("source_id", "edition"),)

class ProspectiveSkillProjection(Base):
    __tablename__ = "prospective_skill_projections"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    edition_id: Mapped[str] = mapped_column(ForeignKey("prospective_editions.id", ondelete="CASCADE"), index=True)
    skill_id: Mapped[str | None] = mapped_column(ForeignKey("skills.id"), index=True)
    source_label: Mapped[str] = mapped_column(String(300))
    category: Mapped[str | None] = mapped_column(String(100))
    central_share: Mapped[float | None] = mapped_column(Float)
    projected_change: Mapped[float] = mapped_column(Float)
    figure_table: Mapped[str] = mapped_column(String(200))
    geography: Mapped[str] = mapped_column(String(100), default="Global")
    sector: Mapped[str | None] = mapped_column(String(150))
    mapping_method: Mapped[str | None] = mapped_column(String(80))
    mapping_confidence: Mapped[float | None] = mapped_column(Float)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    __table_args__ = (UniqueConstraint("edition_id", "source_label", "figure_table", "geography", "sector"),)

class TrendScore(Base):
    __tablename__ = "trend_scores"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    entity_type: Mapped[str] = mapped_column(String(30), index=True)
    entity_id: Mapped[str] = mapped_column(String(36), index=True)
    period: Mapped[date] = mapped_column(Date, index=True)
    score: Mapped[float] = mapped_column(Float)
    growth: Mapped[float] = mapped_column(Float)
    acceleration: Mapped[float] = mapped_column(Float)
    volume: Mapped[float] = mapped_column(Float)
    geographic_spread: Mapped[float] = mapped_column(Float)
    source_confidence: Mapped[float] = mapped_column(Float)
    raw_growth: Mapped[float | None] = mapped_column(Float)
    calculation_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    method_version: Mapped[str] = mapped_column(String(20), default="1.0")
    is_official: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (UniqueConstraint("entity_type", "entity_id", "period", "method_version"),)
