from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from fastapi.responses import FileResponse

from app.api.deps import get_repository
from app.api.routes.games import load_game
from app.config import Settings, get_settings
from app.models import Game, GameImage, ImageKind
from app.repositories import Repository
from app.schemas.dto import ImageKindName, ImageOut
from app.schemas.mappers import image_to_out
from app.services.image_service import ImageLimits, UploadError, delete_image_file, image_path, save_image

router = APIRouter(prefix="/games/{game_id}/images", tags=["images"])


def _find(game: Game, image_id: str) -> GameImage:
    for i in game.images:
        if i.id == image_id:
            return i
    raise HTTPException(status_code=404, detail="Image not found")


def limits_for(kind: ImageKind, s: Settings) -> ImageLimits:
    return ImageLimits(
        max_count=s.max_key_art if kind == ImageKind.KEY_ART else s.max_screenshots,
        max_bytes=s.max_image_upload_bytes,
        max_dimension=s.max_image_dimension,
        max_pixels=s.max_image_pixels,
    )


@router.post("", response_model=ImageOut, status_code=status.HTTP_201_CREATED)
async def upload_image(
    file: UploadFile = File(...),
    kind: ImageKindName = Form("screenshot"),
    game: Game = Depends(load_game),
    repo: Repository = Depends(get_repository),
    settings: Settings = Depends(get_settings),
) -> ImageOut:
    data = await file.read(settings.max_image_upload_bytes + 1)
    k = ImageKind(kind)
    try:
        img = save_image(game, k, file.filename or "upload", data, settings.upload_dir, limits_for(k, settings))
    except UploadError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail) from e
    repo.update_game(game)
    return image_to_out(img)


@router.get("", response_model=list[ImageOut])
def list_images(kind: ImageKindName | None = None, game: Game = Depends(load_game)) -> list[ImageOut]:
    return [image_to_out(i) for i in game.images if kind is None or i.kind == kind]


@router.get("/{image_id}", response_class=FileResponse)
def get_image(
    image_id: str, game: Game = Depends(load_game), settings: Settings = Depends(get_settings)
) -> FileResponse:
    img = _find(game, image_id)
    path = image_path(settings.upload_dir, img)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Image file missing")
    return FileResponse(
        path,
        media_type=img.content_type,
        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, max-age=3600"},
    )


@router.delete("/{image_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_image(
    image_id: str,
    game: Game = Depends(load_game),
    repo: Repository = Depends(get_repository),
    settings: Settings = Depends(get_settings),
) -> Response:
    img = _find(game, image_id)
    game.images = [i for i in game.images if i.id != image_id]
    repo.update_game(game)
    delete_image_file(settings.upload_dir, img)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
