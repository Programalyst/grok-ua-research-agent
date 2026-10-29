from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_provider, get_repository
from app.api.routes.games import load_game
from app.models import Game
from app.providers import LLMProvider
from app.repositories import Repository
from app.schemas.dto import ScanCreate, ScanOut
from app.schemas.mappers import scan_to_out
from app.services.scan_service import ScanService

router = APIRouter(tags=["scans"])


@router.post("/games/{game_id}/scans", response_model=ScanOut, status_code=status.HTTP_201_CREATED)
async def run_scan(
    body: ScanCreate | None = None,
    game: Game = Depends(load_game),
    repo: Repository = Depends(get_repository),
    provider: LLMProvider = Depends(get_provider),
) -> ScanOut:
    body = body or ScanCreate()
    scan = await ScanService(repo, provider).run_scan(game, body.max_posts)
    return scan_to_out(scan)


@router.get("/games/{game_id}/scans", response_model=list[ScanOut])
def list_scans(game: Game = Depends(load_game), repo: Repository = Depends(get_repository)) -> list[ScanOut]:
    return [scan_to_out(s) for s in repo.list_scans(game.id)]


@router.get("/scans/{scan_id}", response_model=ScanOut)
def get_scan(scan_id: str, repo: Repository = Depends(get_repository)) -> ScanOut:
    scan = repo.get_scan(scan_id)
    if scan is None:
        raise HTTPException(status_code=404, detail="Scan not found")
    return scan_to_out(scan)
