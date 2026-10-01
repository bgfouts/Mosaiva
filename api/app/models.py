from datetime import date, datetime, timezone

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SettingsRow(Base):
    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    timezone: Mapped[str] = mapped_column(String(80), default="UTC")
    display_name: Mapped[str] = mapped_column(String(120), default="")


class Hypothesis(Base):
    __tablename__ = "hypotheses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    statement: Mapped[str] = mapped_column(Text, default="")
    why_it_fits: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[str] = mapped_column(Text, default="")
    likely_role: Mapped[str] = mapped_column(Text, default="")
    position: Mapped[int] = mapped_column(Integer, default=0)
    domains: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(32), default="active")
    probability: Mapped[float] = mapped_column(Float, default=0.5)
    why_moved: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    evidence: Mapped[list["Evidence"]] = relationship(
        back_populates="hypothesis",
        cascade="all, delete-orphan",
    )
    interventions: Mapped[list["Intervention"]] = relationship(
        secondary="intervention_hypotheses",
        back_populates="hypotheses",
    )


class Evidence(Base):
    __tablename__ = "evidence"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    text: Mapped[str] = mapped_column(Text)
    direction: Mapped[str] = mapped_column(String(32))
    strength: Mapped[str] = mapped_column(String(32))
    hypothesis_id: Mapped[int | None] = mapped_column(ForeignKey("hypotheses.id", ondelete="CASCADE"))
    session_id: Mapped[int | None] = mapped_column(ForeignKey("coach_sessions.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    hypothesis: Mapped[Hypothesis | None] = relationship(back_populates="evidence")


class Intervention(Base):
    __tablename__ = "interventions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(32))
    dose: Mapped[str] = mapped_column(Text, default="")
    position: Mapped[int] = mapped_column(Integer, default=0)
    schedule: Mapped[str] = mapped_column(Text, default="")
    clinician_prescribed: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(32), default="active")
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    stop_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    benefit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    side_effect_burden: Mapped[int | None] = mapped_column(Integer, nullable=True)
    side_effect_notes: Mapped[str] = mapped_column(Text, default="")
    clinician_task: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    hypotheses: Mapped[list[Hypothesis]] = relationship(
        secondary="intervention_hypotheses",
        back_populates="interventions",
    )


class InterventionHypothesis(Base):
    __tablename__ = "intervention_hypotheses"

    intervention_id: Mapped[int] = mapped_column(
        ForeignKey("interventions.id", ondelete="CASCADE"), primary_key=True
    )
    hypothesis_id: Mapped[int] = mapped_column(
        ForeignKey("hypotheses.id", ondelete="CASCADE"), primary_key=True
    )


class ResearchItem(Base):
    __tablename__ = "research_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(500))
    journal: Mapped[str] = mapped_column(String(200), default="")
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pdf_url: Mapped[str] = mapped_column(Text)
    local_path: Mapped[str] = mapped_column(Text, default="")
    excerpt: Mapped[str] = mapped_column(Text, default="")
    query: Mapped[str] = mapped_column(Text, default="")
    relevance_note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    hypotheses: Mapped[list[Hypothesis]] = relationship(secondary="research_hypotheses")
    interventions: Mapped[list[Intervention]] = relationship(secondary="research_interventions")


class ResearchHypothesis(Base):
    __tablename__ = "research_hypotheses"

    research_id: Mapped[int] = mapped_column(
        ForeignKey("research_items.id", ondelete="CASCADE"), primary_key=True
    )
    hypothesis_id: Mapped[int] = mapped_column(
        ForeignKey("hypotheses.id", ondelete="CASCADE"), primary_key=True
    )


class ResearchIntervention(Base):
    __tablename__ = "research_interventions"

    research_id: Mapped[int] = mapped_column(
        ForeignKey("research_items.id", ondelete="CASCADE"), primary_key=True
    )
    intervention_id: Mapped[int] = mapped_column(
        ForeignKey("interventions.id", ondelete="CASCADE"), primary_key=True
    )


class CoachSession(Base):
    __tablename__ = "coach_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    status: Mapped[str] = mapped_column(String(32), default="active")
    transcript: Mapped[list] = mapped_column(JSON, default=list)
    urgent: Mapped[bool] = mapped_column(Boolean, default=False)
    ask_since_last: Mapped[bool] = mapped_column(Boolean, default=False)
    plan_status: Mapped[str] = mapped_column(String(32), default="pending")
    planned_questions: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    captures: Mapped[list["Capture"]] = relationship(back_populates="session", cascade="all, delete-orphan")


class Capture(Base):
    __tablename__ = "captures"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("coach_sessions.id", ondelete="CASCADE"))
    tool_name: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    session: Mapped[CoachSession] = relationship(back_populates="captures")


class MosaicReview(Base):
    __tablename__ = "mosaic_reviews"
    __table_args__ = (UniqueConstraint("week_start", name="uq_mosaic_week"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    week_start: Mapped[date] = mapped_column(Date, unique=True)
    hypothesis_updates: Mapped[list] = mapped_column(JSON, default=list)
    recommendation: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(32), default="proposed")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
