from __future__ import annotations

from datetime import datetime
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ConfigVersion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "config_versions"
    __table_args__ = (
        sa.UniqueConstraint("config_kind", "version", name="uq_config_kind_version"),
        sa.UniqueConstraint("content_sha256", name="uq_config_content_hash"),
    )

    config_kind: Mapped[str] = mapped_column(sa.String(120), nullable=False)
    version: Mapped[str] = mapped_column(sa.String(80), nullable=False)
    content_sha256: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    source_path: Mapped[str | None] = mapped_column(sa.String(512))
    content_text: Mapped[str] = mapped_column(sa.Text, nullable=False)
    activated_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False)


class ScoringConfig(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "scoring_configs"
    __table_args__ = (
        sa.UniqueConstraint("config_version_id", "model_name", name="uq_scoring_config_version_model"),
    )

    config_version_id: Mapped[UUID] = mapped_column(
        sa.ForeignKey("config_versions.id", ondelete="RESTRICT"), nullable=False
    )
    model_name: Mapped[str] = mapped_column(sa.String(160), nullable=False)
    model_version: Mapped[str] = mapped_column(sa.String(80), nullable=False)
    pursue_threshold: Mapped[float | None] = mapped_column(sa.Float)
    review_threshold: Mapped[float | None] = mapped_column(sa.Float)
    notes: Mapped[str | None] = mapped_column(sa.Text)
