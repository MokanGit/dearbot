from datetime import datetime, timezone
import uuid
import secrets
from typing import Optional, List, Dict, Any
from sqlalchemy import String, Text, DateTime, ForeignKey, Enum as SQLEnum, Integer, Boolean
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def generate_token() -> str:
    """Generate a URL-safe token with >= 128 bits of cryptographic entropy."""
    # 24 bytes = 192 bits entropy, URL-safe base64 is ~32 chars
    return secrets.token_urlsafe(24)


def generate_uuid() -> str:
    return str(uuid.uuid4())


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Document(Base):
    """Canonical professional knowledge document synced from Google Drive."""
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    google_file_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(255))
    filename: Mapped[str] = mapped_column(String(255))
    content_markdown: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    classification: Mapped[str] = mapped_column(String(32), default="internal", index=True)  # "public" or "internal"
    classification_source: Mapped[str] = mapped_column(String(32), default="auto_default")  # "auto_default", "admin_override"
    manually_approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    last_modified: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    last_synced: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class Application(Base):
    """An application-specific context linking a unique token to role metadata."""
    __tablename__ = "applications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True, default=generate_token)
    company: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(255))
    job_description: Mapped[str] = mapped_column(Text)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cv_version: Mapped[str] = mapped_column(String(50), default="2026-09")
    pdf_path: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    cover_letter_path: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    cover_letter_filename: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    cover_letter_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    candidate_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    candidate_headline: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    cover_letter_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    suggested_questions: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    interactions: Mapped[List["Interaction"]] = relationship(
        "Interaction", back_populates="application", cascade="all, delete-orphan"
    )
    documents: Mapped[List["ApplicationDocument"]] = relationship(
        "ApplicationDocument", back_populates="application", cascade="all, delete-orphan"
    )

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None


class ApplicationDocument(Base):
    """An additional supporting document attached to an application package."""
    __tablename__ = "application_documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    application_id: Mapped[str] = mapped_column(String(36), ForeignKey("applications.id"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    filename: Mapped[str] = mapped_column(String(255))
    file_path: Mapped[str] = mapped_column(String(512))
    file_size: Mapped[int] = mapped_column(Integer, default=0)
    mime_type: Mapped[str] = mapped_column(String(100), default="application/octet-stream")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    application: Mapped["Application"] = relationship("Application", back_populates="documents")


class Interaction(Base):
    """Access or query interaction logged against an application token."""
    __tablename__ = "interactions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    application_id: Mapped[str] = mapped_column(String(36), ForeignKey("applications.id"), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    event_type: Mapped[str] = mapped_column(String(50), index=True)  # PROFILE_VIEW, PROFILE_JSON, QUESTION, MCP_CALL
    question: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    answer: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    confidence: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # high, medium, low
    evidence_sources: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON-encoded array of excerpts
    client_type: Mapped[str] = mapped_column(String(50), default="unknown")  # browser, ai_agent, known_bot, unknown
    client_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # ChatGPT, Claude, Perplexity, etc.
    user_agent: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    request_id: Mapped[str] = mapped_column(String(64), default=generate_uuid)
    access_method: Mapped[str] = mapped_column(String(50), default="web", index=True)  # web, get, api, mcp, webmcp
    tool: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # ask_cv, get_cv_summary, get_experience, etc.
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # execution latency in ms

    # Rich Network & Organization Intelligence
    ip_address: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    reverse_dns: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    geo_country: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    geo_city: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    geo_region: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    isp: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    organization: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    asn: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # HTTP Context
    referer: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    accept_language: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Client Hardware & Fingerprint Telemetry
    device_fingerprint: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    device_metadata: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON-encoded hardware & engagement profile

    application: Mapped["Application"] = relationship("Application", back_populates="interactions")
