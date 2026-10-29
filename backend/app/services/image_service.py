"""Image upload handling: validate, normalize (WebP->PNG, strip metadata, downscale), store on disk."""

import io
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from app.models import Game, GameImage, ImageKind

# Formats accepted from users -> what we store (xAI vision accepts only PNG/JPEG).
_ACCEPTED = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp"}
_EXT = {"image/png": ".png", "image/jpeg": ".jpg"}


class UploadError(ValueError):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


@dataclass(frozen=True)
class ImageLimits:
    max_count: int
    max_bytes: int
    max_dimension: int
    max_pixels: int


@dataclass(frozen=True)
class NormalizedImage:
    data: bytes
    content_type: str
    width: int
    height: int


def normalize_image(data: bytes, max_dimension: int, max_pixels: int) -> NormalizedImage:
    """Decode with Pillow, reject non-images/bombs, re-encode as PNG or JPEG, downscale to max_dimension."""
    try:
        with Image.open(io.BytesIO(data)) as probe:
            fmt = probe.format
            w, h = probe.size
            if fmt not in _ACCEPTED:
                raise UploadError(415, "Only PNG, JPEG or WebP images are allowed")
            if w * h > max_pixels:
                raise UploadError(413, f"Image too large ({w}x{h}); max {max_pixels:,} pixels")
            probe.verify()
        with Image.open(io.BytesIO(data)) as img:
            img.load()
            img = ImageOps.exif_transpose(img)
            if getattr(img, "n_frames", 1) > 1:
                img.seek(0)
            img.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)
            out = io.BytesIO()
            if fmt == "JPEG":
                img.convert("RGB").save(out, format="JPEG", quality=90, optimize=True)
                content_type = "image/jpeg"
            else:  # PNG, or WebP converted to PNG (keeps alpha)
                if img.mode not in ("RGB", "RGBA", "L", "LA", "P"):
                    img = img.convert("RGBA")
                img.save(out, format="PNG", optimize=True)
                content_type = "image/png"
            return NormalizedImage(out.getvalue(), content_type, img.width, img.height)
    except UploadError:
        raise
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, ValueError, SyntaxError) as e:
        raise UploadError(415, "File is not a valid PNG, JPEG or WebP image") from e


def save_image(
    game: Game, kind: ImageKind, filename: str, data: bytes, upload_dir: Path, limits: ImageLimits
) -> GameImage:
    label = "key art images" if kind == ImageKind.KEY_ART else "screenshots"
    if len(game.images_of(kind)) >= limits.max_count:
        raise UploadError(409, f"Maximum of {limits.max_count} {label} per game")
    if not data:
        raise UploadError(422, "Empty file")
    if len(data) > limits.max_bytes:
        raise UploadError(413, f"File exceeds {limits.max_bytes // (1024 * 1024)} MB limit")
    norm = normalize_image(data, limits.max_dimension, limits.max_pixels)
    img = GameImage(
        game_id=game.id,
        kind=kind,
        filename=Path(filename or "upload").name[:200],
        content_type=norm.content_type,
        size_bytes=len(norm.data),
        width=norm.width,
        height=norm.height,
        stored_name="",
    )
    img.stored_name = f"{img.id}{_EXT[norm.content_type]}"
    target = upload_dir / game.id
    target.mkdir(parents=True, exist_ok=True)
    (target / img.stored_name).write_bytes(norm.data)
    game.images.append(img)
    return img


def image_path(upload_dir: Path, img: GameImage) -> Path:
    return upload_dir / img.game_id / img.stored_name


def delete_image_file(upload_dir: Path, img: GameImage) -> None:
    image_path(upload_dir, img).unlink(missing_ok=True)
