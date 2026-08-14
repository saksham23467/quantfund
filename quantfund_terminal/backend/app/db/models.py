"""Multi-tenant SQLAlchemy models.

Tenancy: every business row carries org_id. The dataset catalog + certifications
are global (shared research assets). Research records form a hash-linked,
append-only chain (immutable reproducibility proofs).
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from quantfund_terminal.backend.app.db.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Org(Base):
    __tablename__ = "orgs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    plan: Mapped[str] = mapped_column(String(40), default="trial")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    users: Mapped[list["User"]] = relationship(back_populates="org")
    strategies: Mapped[list["Strategy"]] = relationship(back_populates="org")


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("orgs.id"), index=True)
    email: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    role: Mapped[str] = mapped_column(String(20), default="analyst")  # viewer|analyst|pm|admin
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    org: Mapped[Org] = relationship(back_populates="users")


class Subscription(Base):
    __tablename__ = "subscriptions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("orgs.id"), index=True)
    plan: Mapped[str] = mapped_column(String(40), default="analyst")  # analyst|team|enterprise
    status: Mapped[str] = mapped_column(String(20), default="active")  # active|trialing|past_due|canceled
    seats: Mapped[int] = mapped_column(Integer, default=1)
    mrr_inr: Mapped[float] = mapped_column(Float, default=0.0)
    external_customer_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    renews_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Dataset(Base):
    __tablename__ = "datasets"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dataset_id: Mapped[str] = mapped_column(String(120), index=True)
    dataset_version: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(200))
    source_name: Mapped[str] = mapped_column(String(120))
    source_type: Mapped[str] = mapped_column(String(40))   # EXCHANGE|LICENSED|BROKER|PUBLIC|SYNTHETIC
    source_grade: Mapped[str] = mapped_column(String(40))  # exchange|research|non_exchange
    data_class: Mapped[str] = mapped_column(String(40))    # RESEARCH_DATA|DEVELOPMENT_DATA|DEMO_SYNTHETIC
    asset_class: Mapped[str] = mapped_column(String(40), default="equity")
    coverage_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    coverage_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    content_hash: Mapped[str] = mapped_column(String(120))
    object_uri: Mapped[str | None] = mapped_column(String(300), nullable=True)
    immutable: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    certifications: Mapped[list["Certification"]] = relationship(back_populates="dataset")


class Certification(Base):
    __tablename__ = "certifications"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dataset_pk: Mapped[int] = mapped_column(ForeignKey("datasets.id"), index=True)
    verdict: Mapped[str] = mapped_column(String(40))  # RESEARCH_ELIGIBLE|DEVELOPMENT_ONLY
    research_eligible: Mapped[bool] = mapped_column(Boolean, default=False)
    membership_coverage_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    instrument_identity_coverage: Mapped[float | None] = mapped_column(Float, nullable=True)
    delisted_coverage: Mapped[str | None] = mapped_column(String(40), nullable=True)
    corporate_action_coverage: Mapped[str | None] = mapped_column(String(40), nullable=True)
    calendar_verified: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    leakage_safe: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    reproducible: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    immutable: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    blockers: Mapped[list] = mapped_column(JSON, default=list)
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    dataset: Mapped[Dataset] = relationship(back_populates="certifications")


class Strategy(Base):
    __tablename__ = "strategies"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("orgs.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    family: Mapped[str] = mapped_column(String(40))
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(40), default="DRAFT")  # DRAFT|BACKTESTED|ACCEPTED|REJECTED|RESEARCH_ONLY
    visibility: Mapped[str] = mapped_column(String(20), default="private")  # private|marketplace
    created_by: Mapped[str] = mapped_column(String(200), default="system")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    org: Mapped[Org] = relationship(back_populates="strategies")
    backtests: Mapped[list["Backtest"]] = relationship(back_populates="strategy")


class Backtest(Base):
    __tablename__ = "backtests"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    strategy_id: Mapped[int] = mapped_column(ForeignKey("strategies.id"), index=True)
    dataset_pk: Mapped[int | None] = mapped_column(ForeignKey("datasets.id"), nullable=True)
    start: Mapped[str | None] = mapped_column(String(20), nullable=True)
    end: Mapped[str | None] = mapped_column(String(20), nullable=True)
    cost_bps: Mapped[float] = mapped_column(Float, default=10.0)
    slippage_bps: Mapped[float] = mapped_column(Float, default=5.0)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)  # cagr/sharpe/sortino/...
    dsr: Mapped[float | None] = mapped_column(Float, nullable=True)
    data_class: Mapped[str] = mapped_column(String(40), default="DEMO_SYNTHETIC")
    dataset_hash: Mapped[str] = mapped_column(String(120))
    experiment_hash: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    strategy: Mapped[Strategy] = relationship(back_populates="backtests")


class ResearchRecord(Base):
    """Append-only, hash-linked reproducibility ledger. Never updated/deleted."""

    __tablename__ = "research_records"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[int | None] = mapped_column(ForeignKey("orgs.id"), nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(40))  # backtest|certification|strategy|dataset
    ref_id: Mapped[str] = mapped_column(String(120))
    content_hash: Mapped[str] = mapped_column(String(120), index=True)
    prev_hash: Mapped[str | None] = mapped_column(String(120), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[int | None] = mapped_column(ForeignKey("orgs.id"), nullable=True, index=True)
    actor: Mapped[str] = mapped_column(String(200), default="system")
    action: Mapped[str] = mapped_column(String(80))
    entity_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    entity_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
