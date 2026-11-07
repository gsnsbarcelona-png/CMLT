import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile

IMAGES_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "images"

MAX_IMAGE_BYTES = 5 * 1024 * 1024  # 5 MB, suficiente para un tweet, evita subidas gigantes por error
ALLOWED_EXTENSIONS = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif", ".webp": "image/webp"}

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
