from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_budget, get_provider, get_repository
from app.api.routes.games import load_game
from app.config import Settings, get_settings
from app.models import Game, ImageKind
from app.providers import ImageInput, LLMProvider, ProviderError
from app.repositories import Repository
from app.schemas.dto import GameProfileOut, GameProfileUpdate
from app.schemas.mappers import profile_from_update, profile_to_out
from app.services.budget import BudgetExceededError, DailyBudget
from app.services.image_service import image_path

router = APIRouter(prefix="/games/{game_id}/profile", tags=["profile"])


@router.post("/generate", response_model=GameProfileOut)
async def generate_profile(
    game: Game = Depends(load_game),
    repo: Repository = Depends(get_repository),
    provider: LLMProvider = Depends(get_provider),
    settings: Settings = Depends(get_settings),
    budget: DailyBudget = Depends(get_budget),
) -> GameProfileOut:
    ordered = game.images_of(ImageKind.KEY_ART) + game.images_of(ImageKind.SCREENSHOT)
    images = [
        ImageInput(path=image_path(settings.upload_dir, i), content_type=i.content_type, kind=i.kind.value)
        for i in ordered
    ]
    try:
        budget.check()
    except BudgetExceededError as e:
        raise HTTPException(status_code=429, detail=str(e)) from e
    try:
        profile = await provider.generate_profile(game, images)
    except ProviderError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    except NotImplementedError as e:
        raise HTTPException(status_code=501, detail=str(e)) from e
    budget.record(
        cost_usd=profile.cost_usd,
        provider=profile.generated_by,
        model=profile.model,
        purpose="profile_generation",
        game_id=game.id,
    )
    game.profile = profile
    repo.update_game(game)
    return profile_to_out(profile)


@router.get("", response_model=GameProfileOut)
def get_profile(game: Game = Depends(load_game)) -> GameProfileOut:
    if game.profile is None:
        raise HTTPException(status_code=404, detail="Profile not generated yet")
    return profile_to_out(game.profile)


@router.put("", response_model=GameProfileOut)
def put_profile(
    body: GameProfileUpdate, game: Game = Depends(load_game), repo: Repository = Depends(get_repository)
) -> GameProfileOut:
    game.profile = profile_from_update(game.id, body, game.profile)
    repo.update_game(game)
    return profile_to_out(game.profile)
