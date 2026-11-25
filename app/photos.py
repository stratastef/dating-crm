"""Photos: the user's own photos, ranked by Claude, with light edits offered as previews.

Claude only looks at the photos and writes text. Every image the server returns is the uploaded file, or
that file after a crop, an exposure change and a colour change done by Pillow. No image is generated, and
nothing here writes to a dating app.
"""

import io
import os
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from PIL import Image, ImageEnhance, ImageOps
from pydantic import BaseModel, Field, TypeAdapter, ValidationError, field_validator
from sqlalchemy import text

from app import llm
from app.auth import CurrentUser, Db

router = APIRouter()

MAX_BYTES = 10 * 1024 * 1024
_FORMATS = {"JPEG": "image/jpeg", "PNG": "image/png"}  # Pillow format -> content type

_COLUMNS = "id, rank, reason, suggested_edit, edit"

_Light = Annotated[float, Field(ge=0.5, le=1.5)]  # 1 changes nothing; the bounds keep an edit light


class Edit(BaseModel):
    """A light edit of one photo. Applied by `_edited()` with Pillow, to the uploaded file only."""

    # Left, top, right, bottom as fractions of the width and height; null keeps the whole photo.
    crop: tuple[float, float, float, float] | None = None
    exposure: _Light = 1  # below 1 is darker, above 1 brighter
    colour: _Light = 1  # below 1 is less saturated, above 1 more

    @field_validator("crop")
    @classmethod
    def _inside_the_photo(cls, crop):
        if crop and not (0 <= crop[0] < crop[2] <= 1 and 0 <= crop[1] < crop[3] <= 1):
            raise ValueError("crop must be left < right and top < bottom, all from 0 to 1")
        return crop


class Photo(BaseModel):
    id: int
    rank: int | None  # 1 is the best photo; null until the photos are ranked
    reason: str | None  # why the photo has that rank
    suggested_edit: Edit | None  # the edit on offer; null when there is none to accept or reject
    edit: Edit | None  # the edit the user accepted; null while the photo is as uploaded


class Decision(BaseModel):
    accept: bool


def _path(user_id: int, photo_id: int) -> Path:
    """Where a photo's file is. Both parts are database IDs, never text from the client."""
    return Path(os.environ.get("PHOTOS_DIR", "photos")) / str(user_id) / str(photo_id)


async def _upload(request: Request) -> bytes:
    """The request body, read only up to the size limit."""
    data = bytearray()
    async for chunk in request.stream():
        data += chunk
        if len(data) > MAX_BYTES:
            raise HTTPException(status_code=413, detail=f"a photo may be at most {MAX_BYTES} bytes")
    return bytes(data)


@router.post("/photos", response_model=Photo, status_code=201)
def upload(request: Request, data: Annotated[bytes, Depends(_upload)], user: CurrentUser, db: Db):
    """Store one photo. The body is the JPEG or PNG file itself, with its type in `Content-Type`."""
    content_type = request.headers.get("content-type")
    if content_type not in _FORMATS.values():
        raise HTTPException(status_code=415, detail="a photo must be image/jpeg or image/png")
    try:
        with Image.open(io.BytesIO(data), formats=[*_FORMATS]) as image:
            image.verify()
            actual = _FORMATS[image.format]
    except Exception:  # Pillow raises many types for a broken file
        raise HTTPException(status_code=422, detail="the file is not a readable JPEG or PNG")
    if actual != content_type:
        raise HTTPException(status_code=422, detail=f"the file is {actual}, not {content_type}")
    photo = db.execute(
        text(f"INSERT INTO photos (user_id, content_type) VALUES (:user_id, :content_type) RETURNING {_COLUMNS}"),
        {"user_id": user.id, "content_type": content_type},
    ).one()
    path = _path(user.id, photo.id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return photo


@router.get("/photos", response_model=list[Photo])
def photos(user: CurrentUser, db: Db):
    """The user's photos, best first once ranked. Unranked photos come last, oldest first."""
    return db.execute(
        text(f"SELECT {_COLUMNS} FROM photos WHERE user_id = :user_id ORDER BY rank NULLS LAST, id"),
        {"user_id": user.id},
    ).all()


class _Ranked(BaseModel):
    id: int
    reason: str
    edit: Edit | None = None


_RANKING = TypeAdapter(list[_Ranked])

_SYSTEM = (
    "You rank one person's own photos for their dating profile, best first. Judge what a stranger swiping"
    " would see: a clear face, light, expression, what the photo says about the person, and variety across"
    " the set. Give each photo one short, honest reason for its place, written to the person. Rank every"
    " photo exactly once. Where a light edit would help a photo, suggest one: a crop as"
    " [left, top, right, bottom] in fractions of the width and height from 0 to 1, an exposure factor and a"
    " colour (saturation) factor, both from 0.5 to 1.5 where 1 changes nothing. The edit is applied to the"
    " original photo by ordinary image code; use null when the photo needs none. Reply with JSON only, in"
    ' the shape [{"id": <photo id>, "reason": "...", "edit": {"crop": [0, 0, 1, 1] or null, "exposure": 1,'
    ' "colour": 1} or null}], best photo first.'
)


def _for_claude(path: Path) -> tuple[str, bytes]:
    """The photo scaled down to at most 1024 pixels a side, as JPEG: enough to judge it, and cheap to send."""
    with Image.open(path) as image:
        image = ImageOps.exif_transpose(image).convert("RGB")
        image.thumbnail((1024, 1024))
        out = io.BytesIO()
        image.save(out, "JPEG", quality=90)
    return "image/jpeg", out.getvalue()


@router.post("/photos/rank", response_model=list[Photo])
def rank(user: CurrentUser, db: Db):
    """Have Claude rank all the user's photos and store each photo's rank and reason. Returns them best first."""
    ids = db.execute(text("SELECT id FROM photos WHERE user_id = :user_id ORDER BY id"), {"user_id": user.id}).scalars().all()
    if not ids:
        raise HTTPException(status_code=409, detail="upload a photo first")
    prompt = f"The photos are attached in this order. Their ids, in the same order: {', '.join(map(str, ids))}."
    # shortcut: every photo goes into one request, made inside the route. Claude takes about 100 images per
    # request, so cap the photos per user or rank in a job if someone uploads that many.
    reply = llm.call(
        db, user.id, "photo_ranking", _SYSTEM, prompt, images=[_for_claude(_path(user.id, id)) for id in ids]
    ).text
    try:
        ranking = _RANKING.validate_json(reply)
    except ValidationError:
        ranking = []
    if sorted(ranked.id for ranked in ranking) != ids:
        raise HTTPException(status_code=502, detail="the ranking was not usable, try again")
    # A new ranking replaces the edit on offer. An edit the user already accepted stays.
    db.execute(
        text(
            "UPDATE photos SET rank = :rank, reason = :reason, suggested_edit = CAST(:edit AS jsonb)"
            " WHERE id = :id AND user_id = :user_id"
        ),
        [
            {
                "rank": rank,
                "reason": ranked.reason,
                "edit": ranked.edit and ranked.edit.model_dump_json(),
                "id": ranked.id,
                "user_id": user.id,
            }
            for rank, ranked in enumerate(ranking, start=1)
        ],
    )
    return photos(user, db)


def _photo(db, user_id: int, photo_id: int):
    photo = db.execute(
        text("SELECT content_type, suggested_edit, edit FROM photos WHERE id = :id AND user_id = :user_id"),
        {"id": photo_id, "user_id": user_id},
    ).one_or_none()
    if not photo:
        raise HTTPException(status_code=404, detail="photo not found")
    return photo


def _edited(path: Path, edit: Edit) -> bytes:
    """The uploaded file after the edit, in the file's own format. Only Pillow arithmetic on its pixels."""
    with Image.open(path) as original:
        format = original.format
        image = ImageOps.exif_transpose(original).convert("RGB")
    if edit.crop:
        left, top, right, bottom = edit.crop
        image = image.crop(
            (round(left * image.width), round(top * image.height), round(right * image.width), round(bottom * image.height))
        )
    image = ImageEnhance.Brightness(image).enhance(edit.exposure)
    image = ImageEnhance.Color(image).enhance(edit.colour)
    out = io.BytesIO()
    image.save(out, format, quality=95)  # PNG ignores quality
    return out.getvalue()


@router.get("/photos/{photo_id}/image")
def image(photo_id: int, user: CurrentUser, db: Db):
    """The photo with the edit the user accepted, or the file as uploaded when they accepted none."""
    photo = _photo(db, user.id, photo_id)
    path = _path(user.id, photo_id)
    data = _edited(path, Edit.model_validate(photo.edit)) if photo.edit else path.read_bytes()
    return Response(data, media_type=photo.content_type)


@router.get("/photos/{photo_id}/preview")
def preview(photo_id: int, user: CurrentUser, db: Db):
    """What the photo would look like with the edit on offer. Changes nothing; `404` when no edit is on offer."""
    photo = _photo(db, user.id, photo_id)
    if not photo.suggested_edit:
        raise HTTPException(status_code=404, detail="no edit on offer for this photo")
    data = _edited(_path(user.id, photo_id), Edit.model_validate(photo.suggested_edit))
    return Response(data, media_type=photo.content_type)


@router.put("/photos/{photo_id}/edit", response_model=Photo)
def decide(photo_id: int, decision: Decision, user: CurrentUser, db: Db):
    """Accept or reject the edit on offer. Accepting makes it the photo's edit; either way the offer is gone.

    The uploaded file is never changed, so a later accepted edit starts from the original again.
    """
    photo = db.execute(
        text(
            f"""
            UPDATE photos SET edit = CASE WHEN :accept THEN suggested_edit ELSE edit END, suggested_edit = NULL
            WHERE id = :id AND user_id = :user_id AND suggested_edit IS NOT NULL
            RETURNING {_COLUMNS}
            """
        ),
        {"accept": decision.accept, "id": photo_id, "user_id": user.id},
    ).one_or_none()
    if not photo:
        raise HTTPException(status_code=404, detail="no edit on offer for this photo")
    return photo
