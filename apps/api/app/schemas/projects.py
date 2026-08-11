from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from app.domain.states import ProjectState
from app.schemas.common import EntityRead


class ProjectRead(EntityRead):
    project_group_id: UUID | None = None
    canonical_name: str
    normalized_name: str
    canonical_key: str
    source_system: str | None = None
    external_id: str | None = None
    state: ProjectState
    stage: str | None = None
    category: str | None = None
    city: str | None = None
    region: str | None = None
    country_code: str | None = None
    reported_value: Decimal | None = None
    currency_code: str | None = None
    start_date: date | None = None
    completion_date: date | None = None
    is_synthetic: bool
