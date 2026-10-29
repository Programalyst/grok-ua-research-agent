from fastapi import APIRouter, Depends, Query

from app.api.deps import get_repository
from app.api.routes.games import load_game
from app.models import Game
from app.repositories import Repository
from app.schemas.dto import PostOut
from app.schemas.mappers import post_to_out

router = APIRouter(tags=["posts"])


@router.get("/games/{game_id}/posts", response_model=list[PostOut])
def list_posts(
    game: Game = Depends(load_game),
    repo: Repository = Depends(get_repository),
    sentiment: str | None = None,
    category: str | None = None,
    language: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[PostOut]:
    posts = repo.list_posts(game.id)
    if sentiment:
        posts = [p for p in posts if p.sentiment.value == sentiment]
    if category:
        posts = [p for p in posts if p.category.value == category]
    if language:
        posts = [p for p in posts if p.language == language]
    return [post_to_out(p) for p in posts[:limit]]
