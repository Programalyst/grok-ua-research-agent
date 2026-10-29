from fastapi import APIRouter, Depends

from app.api.deps import get_repository
from app.api.routes.games import load_game
from app.models import Game
from app.repositories import Repository
from app.schemas.dto import InsightsOut
from app.schemas.mappers import insights_to_out
from app.services.insights_service import build_insights

router = APIRouter(tags=["insights"])


@router.get("/games/{game_id}/insights", response_model=InsightsOut)
def get_insights(game: Game = Depends(load_game), repo: Repository = Depends(get_repository)) -> InsightsOut:
    return insights_to_out(build_insights(game.id, repo.list_posts(game.id)))
