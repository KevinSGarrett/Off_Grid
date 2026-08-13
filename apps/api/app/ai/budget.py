from __future__ import annotations

import json
import math
from datetime import datetime, time, timezone
from decimal import Decimal
from typing import Mapping

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.ai.config import ModelRoute
from app.ai.types import UsageMetrics
from app.models import AIUsage

MILLION = Decimal("1000000")


def estimate_usage_cost(route: ModelRoute, usage: UsageMetrics) -> Decimal:
    cached = min(max(usage.cached_input_tokens, 0), max(usage.input_tokens, 0))
    uncached = max(usage.input_tokens - cached, 0)
    cost = (
        Decimal(uncached) * route.input_usd_per_million
        + Decimal(cached) * route.cached_input_usd_per_million
        + Decimal(max(usage.output_tokens, 0)) * route.output_usd_per_million
    ) / MILLION
    return cost.quantize(Decimal("0.000001"))


def estimate_request_cost(
    route: ModelRoute,
    request: Mapping[str, object],
    *,
    max_output_tokens: int,
) -> Decimal:
    serialized = json.dumps(request, sort_keys=True, default=str, separators=(",", ":"))
    # Conservative preflight approximation only. Actual usage from the API replaces it afterward.
    input_tokens = max(1, math.ceil(len(serialized) / 4))
    return estimate_usage_cost(
        route,
        UsageMetrics(input_tokens=input_tokens, output_tokens=max_output_tokens),
    )


class DailyBudgetGuard:
    def __init__(self, session: Session, daily_budget_usd: Decimal):
        self.session = session
        self.daily_budget_usd = daily_budget_usd

    def spent_today(self, now: datetime | None = None) -> Decimal:
        now = now or datetime.now(timezone.utc)
        start = datetime.combine(now.date(), time.min, tzinfo=timezone.utc)
        end = datetime.combine(now.date(), time.max, tzinfo=timezone.utc)
        value = self.session.scalar(
            sa.select(sa.func.coalesce(sa.func.sum(AIUsage.estimated_cost_usd), 0)).where(
                AIUsage.created_at >= start,
                AIUsage.created_at <= end,
            )
        )
        return Decimal(str(value or 0))

    def allows(self, estimated_increment: Decimal, *, now: datetime | None = None) -> bool:
        if self.daily_budget_usd <= 0:
            return False
        return self.spent_today(now) + estimated_increment <= self.daily_budget_usd
