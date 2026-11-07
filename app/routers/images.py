import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.services import card_service

IMAGES_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "images"

MAX_IMAGE_BYTES = 5 * 1024 * 1024  # 5 MB, suficiente para un tweet, evita subidas gigantes por error
ALLOWED_EXTENSIONS = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif", ".webp": "image/webp"}

MAX_CARD_ROWS = 12

router = APIRouter(prefix="/api/images", tags=["images"])


def _extension_for(upload: UploadFile) -> str:
    """Deriva la extension del content-type declarado (mas confiable que
    confiar en el nombre de archivo original, que el navegador puede mandar
    vacio o con cualquier cosa)."""
    content_type = (upload.content_type or "").lower()
    for ext, mime in ALLOWED_EXTENSIONS.items():
        if content_type == mime:
            return ext
    raise HTTPException(
        status_code=400,
        detail="Formato de imagen no soportado (usa PNG, JPG, GIF o WEBP).",
    )


@router.post("")
async def upload_image(file: UploadFile) -> dict:
    ext = _extension_for(file)

    contents = await file.read(MAX_IMAGE_BYTES + 1)
    if not contents:
        raise HTTPException(status_code=400, detail="El archivo está vacío.")
    if len(contents) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=400, detail="La imagen supera el límite de 5 MB.")

    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}{ext}"
    (IMAGES_DIR / filename).write_bytes(contents)

    return {"image_url": f"/data/images/{filename}"}


# --- Tarjetas generadas (Resultados / Top 3) --------------------------------
class ResultsCardMatch(BaseModel):
    team1: str = Field(min_length=1, max_length=40)
    team2: str = Field(min_length=1, max_length=40)
    score1: int = Field(ge=0, le=99)
    score2: int = Field(ge=0, le=99)
    block: str = Field(default="", max_length=40)


class ResultsCardRequest(BaseModel):
    title: str = Field(min_length=1, max_length=60)
    subtitle: str = Field(default="", max_length=80)
    matches: list[ResultsCardMatch] = Field(min_length=1, max_length=MAX_CARD_ROWS)


class TopCardEntry(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    value: str = Field(min_length=1, max_length=20)


class TopCardRequest(BaseModel):
    title: str = Field(min_length=1, max_length=60)
    subtitle: str = Field(default="", max_length=80)
    unit: str = Field(default="", max_length=30)
    entries: list[TopCardEntry] = Field(min_length=1, max_length=MAX_CARD_ROWS)


@router.post("/card/results")
def create_results_card(payload: ResultsCardRequest) -> dict:
    png = card_service.render_results_card(payload.title, payload.subtitle, [m.model_dump() for m in payload.matches])
    return {"image_url": card_service.save_card(png, IMAGES_DIR)}


@router.post("/card/top")
def create_top_card(payload: TopCardRequest) -> dict:
    png = card_service.render_top_card(
        payload.title, payload.subtitle, payload.unit, [e.model_dump() for e in payload.entries]
    )
    return {"image_url": card_service.save_card(png, IMAGES_DIR)}
