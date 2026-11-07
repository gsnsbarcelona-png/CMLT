from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from app.db import get_session
from app.models import Template
from app.routers.generate._shared import GenerateResult, _result
from app.routers.templates import render_template

router = APIRouter()


class TemplateGenerateRequest(BaseModel):
    template_id: int
    variables: dict[str, str] = {}


@router.post("/template")
def generate_from_template(
    payload: TemplateGenerateRequest, session: Session = Depends(get_session)
) -> GenerateResult:
    template = session.get(Template, payload.template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="Plantilla no encontrada.")
    try:
        content = render_template(template.template_text, payload.variables)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _result(content)
