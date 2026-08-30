import string

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.db import get_session
from app.models import Template

router = APIRouter(prefix="/api/templates", tags=["templates"])


class _SafeDict(dict):
    def __missing__(self, key):
        raise KeyError(key)


def render_template(template_text: str, variables: dict[str, str]) -> str:
    try:
        return string.Formatter().vformat(template_text, (), _SafeDict(variables))
    except KeyError as exc:
        missing = exc.args[0]
        raise ValueError(f"Falta la variable '{missing}' para renderizar la plantilla.") from exc


@router.get("")
def list_templates(session: Session = Depends(get_session)) -> list[Template]:
    return list(session.exec(select(Template).order_by(Template.created_at.desc())))


@router.post("", status_code=201)
def create_template(template: Template, session: Session = Depends(get_session)) -> Template:
    template.id = None
    session.add(template)
    session.commit()
    session.refresh(template)
    return template


@router.get("/{template_id}")
def get_template(template_id: int, session: Session = Depends(get_session)) -> Template:
    template = session.get(Template, template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="Plantilla no encontrada.")
    return template


@router.put("/{template_id}")
def update_template(template_id: int, payload: Template, session: Session = Depends(get_session)) -> Template:
    template = session.get(Template, template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="Plantilla no encontrada.")
    template.name = payload.name
    template.template_text = payload.template_text
    session.add(template)
    session.commit()
    session.refresh(template)
    return template


@router.delete("/{template_id}", status_code=204)
def delete_template(template_id: int, session: Session = Depends(get_session)) -> None:
    template = session.get(Template, template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="Plantilla no encontrada.")
    session.delete(template)
    session.commit()
