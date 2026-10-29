"""Daily spend guard for paid LLM calls, backed by the provider_usage ledger (survives restarts)."""

from datetime import UTC, datetime

from app.models import UsageRecord
from app.repositories import Repository


class BudgetExceededError(Exception):
    pass


def start_of_local_day(now: datetime | None = None) -> datetime:
    local = (now or datetime.now(UTC)).astimezone()
    return local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)


class DailyBudget:
    def __init__(self, limit_usd: float, repo: Repository) -> None:
        self.limit_usd = limit_usd
        self._repo = repo

    @property
    def spent_usd(self) -> float:
        return self._repo.usage_cost_since(start_of_local_day())

    def check(self) -> None:
        spent = self.spent_usd
        if spent >= self.limit_usd:
            raise BudgetExceededError(
                f"Daily LLM budget of ${self.limit_usd:.2f} reached (spent ${spent:.4f}); try again tomorrow"
            )

    def record(self, *, cost_usd: float | None, provider: str, model: str, purpose: str, game_id: str | None) -> None:
        if cost_usd is None:
            return
        self._repo.add_usage(
            UsageRecord(purpose=purpose, provider=provider, model=model, cost_usd=cost_usd, game_id=game_id)
        )
