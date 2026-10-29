from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.deps import get_repository
from app.config import Settings, get_settings
from app.models import Game
from app.repositories import Repository
from app.schemas.dto import GameCreate, GameOut, GameUpdate
from app.schemas.mappers import apply_game_update, game_from_create, game_to_out
from app.services.image_service import delete_image_file

router = APIRouter(prefix="/games", tags=["games"])


def load_game(game_id: str, repo: Repository = Depends(get_repository)) -> Game:
    game = repo.get_game(game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")
    return game


@router.get("", response_model=list[GameOut])
def list_games(repo: Repository = Depends(get_repository)) -> list[GameOut]:
    return [game_to_out(g) for g in repo.list_games()]


@router.post("", response_model=GameOut, status_code=status.HTTP_201_CREATED)
def create_game(body: GameCreate, repo: Repository = Depends(get_repository)) -> GameOut:
    return game_to_out(repo.add_game(game_from_create(body)))


@router.get("/{game_id}", response_model=GameOut)
def get_game(game: Game = Depends(load_game)) -> GameOut:
    return game_to_out(game)


@router.patch("/{game_id}", response_model=GameOut)
def update_game(
    body: GameUpdate, game: Game = Depends(load_game), repo: Repository = Depends(get_repository)
) -> GameOut:
    return game_to_out(repo.update_game(apply_game_update(game, body)))


@router.delete("/{game_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_game(
    game: Game = Depends(load_game),
    repo: Repository = Depends(get_repository),
    settings: Settings = Depends(get_settings),
) -> Response:
    for img in game.images:
        delete_image_file(settings.upload_dir, img)
    repo.delete_game(game.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
