import uuid
from datetime import UTC, datetime

from geoalchemy2 import Geometry
from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


def utcnow():
    return datetime.now(UTC)


class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String(255), unique=True, nullable=False, index=True)
    full_name = Column(String(255), nullable=True)
    role = Column(String(50), nullable=False, default="CITIZEN", index=True)
    region = Column(String(100), nullable=True, default="mumbai")
    phone = Column(String(32), nullable=True)
    organization = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class WeatherSource(Base):
    __tablename__ = "weather_sources"

    source_id = Column(String(100), primary_key=True)
    name = Column(String(255), nullable=False)
    source_type = Column(String(50), nullable=False)  # RADAR, SATELLITE, GAUGE, NUMERICAL_MODEL
    status = Column(String(50), nullable=False, default="HEALTHY")  # HEALTHY, DEGRADED, OFFLINE
    last_successful_ingestion = Column(DateTime(timezone=True), nullable=True)
    latency_seconds = Column(Float, nullable=True)
    metadata_json = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class ModelRun(Base):
    __tablename__ = "model_runs"

    run_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    model_type = Column(
        String(50), nullable=False, index=True
    )  # NOWCAST, INUNDATION, RISK_AGGREGATION, REPORT_VISION
    model_version = Column(String(50), nullable=False)
    data_version = Column(String(50), nullable=False)
    status = Column(
        String(50), nullable=False, default="RUNNING", index=True
    )  # RUNNING, COMPLETED, FAILED
    started_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    execution_time_ms = Column(Integer, nullable=True)
    metrics_json = Column(JSON, nullable=True)


class RiskCell(Base):
    __tablename__ = "risk_cells"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    h3_cell_id = Column(String(20), nullable=False, index=True)
    valid_time = Column(DateTime(timezone=True), nullable=False, index=True)
    probability = Column(Float, nullable=False, default=0.5)
    confidence = Column(Float, nullable=False)
    risk_level = Column(String(20), nullable=False, index=True)  # LOW, MODERATE, HIGH, SEVERE
    flood_depth_m = Column(Float, nullable=True)
    rainfall_rate_mm_h = Column(Float, nullable=True)
    ward_id = Column(String(100), nullable=True, index=True)
    model_version = Column(String(50), nullable=False)
    data_version = Column(String(50), nullable=False)
    geom = Column(Geometry(geometry_type="POLYGON", srid=4326, spatial_index=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("h3_cell_id", "valid_time", name="uq_risk_cell_valid_time"),
        Index("ix_risk_cells_h3_valid_time", "h3_cell_id", "valid_time"),
    )


class Incident(Base):
    __tablename__ = "incidents"

    incident_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(String(255), nullable=False)
    severity = Column(
        String(20), nullable=False, default="HIGH", index=True
    )  # LOW, MODERATE, HIGH, CRITICAL
    # DETECTED -> OPEN -> ACKNOWLEDGED -> MITIGATING -> RESOLVED -> CLOSED (or DISMISSED)
    status = Column(String(30), nullable=False, default="DETECTED", index=True)
    category = Column(
        String(50), nullable=False
    )  # WATERLOGGING, FLASH_FLOOD, RIVER_BREACH, LANDSLIDE
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    geom = Column(Geometry(geometry_type="POINT", srid=4326, spatial_index=True), nullable=True)
    ward_id = Column(String(100), nullable=True, index=True)
    region = Column(String(100), nullable=True, default="mumbai", index=True)
    reporter_id = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    events = relationship(
        "IncidentEvent",
        back_populates="incident",
        cascade="all, delete-orphan",
        order_by="IncidentEvent.created_at",
    )


class IncidentEvent(Base):
    """
    Append-only incident audit log and lifecycle history.
    """

    __tablename__ = "incident_events"

    event_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    incident_id = Column(
        String(36),
        ForeignKey("incidents.incident_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    actor_id = Column(String(100), nullable=False)
    previous_status = Column(String(30), nullable=True)
    new_status = Column(String(30), nullable=False)
    reason = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)

    incident = relationship("Incident", back_populates="events")


class FieldReport(Base):
    __tablename__ = "field_reports"

    report_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    incident_id = Column(String(36), ForeignKey("incidents.incident_id"), nullable=True, index=True)
    citizen_id = Column(String(100), nullable=True, index=True)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    geom = Column(Geometry(geometry_type="POINT", srid=4326, spatial_index=True), nullable=True)
    description = Column(Text, nullable=True)
    image_url = Column(String(512), nullable=True)
    # DRAFT, PENDING, AI_VERIFIED, HUMAN_VERIFIED, REJECTED
    verification_status = Column(String(30), nullable=False, default="DRAFT", index=True)
    ai_confidence = Column(Float, nullable=True)
    estimated_water_depth_cm = Column(Float, nullable=True)
    verified_by = Column(String(100), nullable=True)
    submitted_at = Column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class FieldReportUpload(Base):
    """
    Direct signed S3/MinIO upload tracking.
    """

    __tablename__ = "field_report_uploads"

    upload_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    citizen_id = Column(String(100), nullable=True)
    report_id = Column(
        String(36),
        ForeignKey("field_reports.report_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    object_key = Column(String(512), nullable=False)
    content_type = Column(String(100), nullable=False, default="image/jpeg")
    file_size_bytes = Column(Integer, nullable=True)
    sha256_checksum = Column(String(64), nullable=True)
    status = Column(
        String(30), nullable=False, default="PENDING"
    )  # PENDING, UPLOADED, FINALIZED, EXPIRED
    presigned_url = Column(Text, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class Alert(Base):
    __tablename__ = "alerts"

    alert_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    headline = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    instruction = Column(Text, nullable=True)
    severity = Column(String(20), nullable=False)  # Extreme, Severe, Moderate, Minor, Unknown
    urgency = Column(String(20), nullable=False)  # Immediate, Expected, Future, Past, Unknown
    certainty = Column(String(20), nullable=False)  # Observed, Likely, Possible, Unlikely, Unknown
    status = Column(
        String(30), nullable=False, default="DRAFT", index=True
    )  # DRAFT, PENDING_APPROVAL, PUBLISHED, CANCELLED
    sent_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    area_description = Column(String(255), nullable=False)
    geom = Column(
        Geometry(geometry_type="MULTIPOLYGON", srid=4326, spatial_index=True), nullable=True
    )
    cap_xml = Column(Text, nullable=True)
    created_by = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class CriticalAsset(Base):
    __tablename__ = "critical_assets"

    asset_id = Column(String(100), primary_key=True)
    name = Column(String(255), nullable=False)
    asset_type = Column(
        String(50), nullable=False
    )  # HOSPITAL, POWER_SUBSTATION, FIRE_STATION, RELIEF_SHELTER, PUMPING_STATION
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    geom = Column(Geometry(geometry_type="POINT", srid=4326, spatial_index=True), nullable=True)
    flood_threshold_m = Column(Float, nullable=False, default=0.5)
    status = Column(
        String(50), nullable=False, default="NORMAL"
    )  # NORMAL, AT_RISK, INUNDATED, OFFLINE
    metadata_json = Column(JSON, nullable=True)


class ResponderTask(Base):
    __tablename__ = "responder_tasks"

    task_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    incident_id = Column(
        String(36), ForeignKey("incidents.incident_id"), nullable=False, index=True
    )
    responder_id = Column(String(100), nullable=False, index=True)
    task_type = Column(
        String(50), nullable=False, default="VERIFY_LOCATION"
    )  # VERIFY_LOCATION, MEASURE_DEPTH, ROAD_BLOCKED, DRAIN_BLOCKED, SUPPORT_REQUEST, ROAD_REOPENED, COMPLETE_TASK
    priority = Column(String(20), nullable=False, default="HIGH")  # CRITICAL, HIGH, MEDIUM, LOW
    status = Column(
        String(30), nullable=False, default="ASSIGNED", index=True
    )  # ASSIGNED, ACKNOWLEDGED, EN_ROUTE, ON_SCENE, COMPLETED
    version = Column(Integer, default=1, nullable=False)  # Optimistic locking
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    evidence_image_url = Column(String(512), nullable=True)
    measured_depth_cm = Column(Float, nullable=True)
    assigned_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    instructions = Column(Text, nullable=True)


class AuditLog(Base):
    __tablename__ = "audit_log"

    log_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    timestamp = Column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)
    actor_id = Column(String(100), nullable=False, index=True)
    actor_role = Column(String(50), nullable=True)
    action = Column(String(100), nullable=False, index=True)
    target_entity = Column(String(100), nullable=False)
    target_id = Column(String(100), nullable=False)
    trace_id = Column(String(64), nullable=True, index=True)
    before_hash = Column(String(64), nullable=True)
    after_hash = Column(String(64), nullable=True)
    supporting_snapshot = Column(JSON, nullable=True)
    changes_json = Column(JSON, nullable=True)


class OutboxEvent(Base):
    __tablename__ = "outbox_events"

    event_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    aggregate_type = Column(String(100), nullable=False, index=True)
    aggregate_id = Column(String(100), nullable=False)
    event_type = Column(String(100), nullable=False, index=True)
    payload_json = Column(JSON, nullable=False)
    processed = Column(Boolean, default=False, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)


class RawWeatherArtifact(Base):
    __tablename__ = "raw_weather_artifacts"

    artifact_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    source_id = Column(String(100), nullable=False, index=True)
    source_timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    ingested_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    sha256_checksum = Column(String(64), nullable=False)
    raw_storage_uri = Column(String(512), nullable=False)
    normalized_uri = Column(String(512), nullable=True)
    provenance_json = Column(JSON, nullable=True)
    is_immutable = Column(Boolean, default=True, nullable=False)


class WatchLocation(Base):
    __tablename__ = "watch_locations"

    location_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(100), nullable=False, index=True)
    label = Column(String(100), nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    h3_cell_id = Column(String(20), nullable=True, index=True)
    ward_id = Column(String(100), nullable=True)
    risk_threshold = Column(String(20), nullable=False, default="HIGH")
    notify_push = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class DevicePushToken(Base):
    __tablename__ = "device_push_tokens"

    token_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(100), nullable=False, index=True)
    expo_push_token = Column(String(255), unique=True, nullable=False, index=True)
    device_os = Column(String(50), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class AppliedMutation(Base):
    __tablename__ = "applied_mutations"

    mutation_id = Column(String(36), primary_key=True)
    client_id = Column(String(100), nullable=False, index=True)
    entity_type = Column(String(50), nullable=False)
    action = Column(String(50), nullable=False)
    status = Column(String(30), nullable=False, default="ACCEPTED")
    applied_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
