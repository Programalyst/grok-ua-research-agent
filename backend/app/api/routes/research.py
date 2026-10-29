from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_budget, get_collector, get_provider, get_repository
from app.api.routes.games import load_game
from app.config import Settings, get_settings
from app.models import Game
from app.providers import LLMProvider
from app.repositories import Repository
from app.schemas.dto import ResearchEstimateOut, ResearchRunCreate, ResearchRunOut, ResearchRunSummaryOut
from app.schemas.mappers import research_summary_to_out, research_to_out
from app.services.budget import BudgetExceededError, DailyBudget
from app.services.research_service import ResearchLimits, ResearchService, comparables_for, plan_tasks
from app.x import Collector

router = APIRouter(tags=["research"])


def _limits(settings: Settings, kind: str, body: ResearchRunCreate | None = None) -> ResearchLimits:
    per = settings.research_max_posts_per_comparable
    total = settings.research_max_posts_per_run
    if body and body.max_posts_per_comparable:
        per = min(per, body.max_posts_per_comparable)
    if body and body.max_posts_total:
        total = min(total, body.max_posts_total)
    searches = settings.research_max_searches
    if body and body.max_searches:
        searches = min(searches, body.max_searches)
    return ResearchLimits(
        collector_kind=kind,
        max_searches=searches,
        cost_per_search_usd=settings.research_grok_cost_per_search_usd,
        max_posts_per_comparable=per,
        max_posts_total=total,
        cost_per_post_usd=settings.x_cost_per_post_usd,
        batch_size=settings.research_batch_size,
        llm_reserve_usd=settings.research_llm_reserve_usd,
    )


@router.get("/games/{game_id}/research/estimate", response_model=ResearchEstimateOut)
def estimate_research(
    max_posts_per_comparable: int | None = None,
    max_posts_total: int | None = None,
    max_searches: int | None = None,
    game: Game = Depends(load_game),
    settings: Settings = Depends(get_settings),
    budget: DailyBudget = Depends(get_budget),
    x: Collector = Depends(get_collector),
    provider: LLMProvider = Depends(get_provider),
) -> ResearchEstimateOut:
    caps = ResearchRunCreate(
        max_posts_per_comparable=max_posts_per_comparable, max_posts_total=max_posts_total, max_searches=max_searches
    )
    lim = _limits(settings, x.kind, caps)
    spent = budget.spent_usd
    remaining = max(0.0, budget.limit_usd - spent)
    return ResearchEstimateOut(
        max_posts_per_comparable=lim.max_posts_per_comparable,
        max_posts_total=lim.max_posts_total,
        cost_per_post_usd=lim.cost_per_post_usd,
        max_x_cost_usd=lim.max_x_cost_usd,
        llm_reserve_usd=lim.llm_reserve_usd,
        max_total_cost_usd=lim.max_total_cost_usd,
        budget_limit_usd=budget.limit_usd,
        budget_spent_today_usd=round(spent, 6),
        budget_remaining_usd=round(remaining, 6),
        can_run=lim.max_total_cost_usd <= remaining,
        x_source=x.source,
        provider=provider.name,
        comparables=comparables_for(game),
        planned_queries=len(plan_tasks(game, lim)),
        collector=x.kind,
        max_searches=lim.max_searches if x.kind == "grok_x_search" else None,
        cost_per_search_usd=lim.cost_per_search_usd if x.kind == "grok_x_search" else None,
        followers_verified=x.followers_verified,
    )


@router.post("/games/{game_id}/research", response_model=ResearchRunOut, status_code=status.HTTP_201_CREATED)
async def run_research(
    body: ResearchRunCreate | None = None,
    game: Game = Depends(load_game),
    repo: Repository = Depends(get_repository),
    settings: Settings = Depends(get_settings),
    budget: DailyBudget = Depends(get_budget),
    x: Collector = Depends(get_collector),
    provider: LLMProvider = Depends(get_provider),
) -> ResearchRunOut:
    if not comparables_for(game):
        raise HTTPException(status_code=422, detail="Add comparable games to the brief first")
    svc = ResearchService(repo, x, provider, budget, _limits(settings, x.kind, body))
    try:
        run = await svc.run(game)
    except BudgetExceededError as e:
        raise HTTPException(status_code=429, detail=str(e)) from e
    posts = repo.list_research_posts(run.id)
    return research_to_out(run, posts, repo.get_authors([p.author_id for p in posts]))


@router.get("/games/{game_id}/research", response_model=list[ResearchRunSummaryOut])
def list_research(
    game: Game = Depends(load_game), repo: Repository = Depends(get_repository)
) -> list[ResearchRunSummaryOut]:
    return [research_summary_to_out(r) for r in repo.list_research_runs(game.id)]


@router.get("/research/{run_id}", response_model=ResearchRunOut)
def get_research(run_id: str, repo: Repository = Depends(get_repository)) -> ResearchRunOut:
    run = repo.get_research_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Research run not found")
    posts = repo.list_research_posts(run.id)
    return research_to_out(run, posts, repo.get_authors([p.author_id for p in posts]))
