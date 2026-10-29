from functools import lru_cache

from fastapi import Depends

from app.config import Settings, get_settings
from app.db import make_engine
from app.providers import FakeProvider, GrokProvider, LLMProvider
from app.repositories import Repository, SqlRepository
from app.services.budget import DailyBudget
from app.x import (
    Collector,
    FakeGrokXSearchCollector,
    FakeXClient,
    GrokXSearchCollector,
    HttpXClient,
    XApiCollector,
    XClient,
)


@lru_cache
def get_repository() -> Repository:
    return SqlRepository(make_engine(get_settings().database_url))


@lru_cache
def get_provider() -> LLMProvider:
    s = get_settings()
    if s.xai_api_key:
        return GrokProvider(
            s.xai_api_key,
            s.xai_base_url,
            s.xai_model,
            timeout=s.xai_timeout_seconds,
            reasoning_effort=s.xai_reasoning_effort or None,
        )
    return FakeProvider()


def get_budget(repo: Repository = Depends(get_repository), settings: Settings = Depends(get_settings)) -> DailyBudget:
    return DailyBudget(settings.daily_budget_usd, repo)


@lru_cache
def get_x_client() -> XClient:
    s = get_settings()
    if s.x_bearer_token:
        return HttpXClient(s.x_bearer_token, s.x_api_base_url, timeout=s.x_timeout_seconds)
    return FakeXClient()


@lru_cache
def get_collector() -> Collector:
    """RESEARCH_COLLECTOR picks the source; without the matching credential a fake is used."""
    s = get_settings()
    if s.research_collector == "x_api":
        return XApiCollector(get_x_client(), s.x_cost_per_post_usd)
    if not s.xai_api_key:
        return FakeGrokXSearchCollector()
    return GrokXSearchCollector(
        s.xai_api_key,
        s.xai_base_url,
        s.xai_model,
        days=s.research_search_days,
        max_tool_calls=s.research_grok_max_tool_calls,
        excluded_handles=s.research_excluded_handles,
        cost_per_post_usd=s.x_cost_per_post_usd,
    )
