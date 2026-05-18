import json
from urllib.parse import parse_qs

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Ticket, TicketEvent
from app.services.ticket_service import update_ticket_status, add_comment, close_ticket

router = APIRouter(tags=["pages"])
templates = Jinja2Templates(directory="app/templates")


def pretty_json(value) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)


templates.env.filters["pretty_json"] = pretty_json


def redirect_to_ticket_actions(ticket_no: str) -> RedirectResponse:
    return RedirectResponse(url=f"/tickets/{ticket_no}#actions", status_code=302)


async def parse_form_data(request: Request) -> dict:
    body = (await request.body()).decode("utf-8")
    parsed = parse_qs(body, keep_blank_values=True)
    return {key: values[-1] if values else "" for key, values in parsed.items()}


@router.get("/tickets")
def ticket_list(request: Request, status: str | None = None, keyword: str | None = None, db: Session = Depends(get_db)):
    query = db.query(Ticket)

    if status:
        query = query.filter(Ticket.status == status)

    if keyword:
        like = f"%{keyword}%"
        query = query.filter(
            Ticket.ticket_no.like(like)
            | Ticket.full_address.like(like)
            | Ticket.user_query.like(like)
            | Ticket.issue_type.like(like)
        )

    tickets = query.order_by(Ticket.created_at.desc()).limit(100).all()

    return templates.TemplateResponse(
        "ticket_list.html",
        {
            "request": request,
            "tickets": tickets,
            "status": status or "",
            "keyword": keyword or "",
        }
    )


@router.get("/tickets/{ticket_no}")
def ticket_detail(request: Request, ticket_no: str, db: Session = Depends(get_db)):
    ticket = db.query(Ticket).filter(Ticket.ticket_no == ticket_no).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="工单不存在")

    events = (
        db.query(TicketEvent)
        .filter(TicketEvent.ticket_no == ticket_no)
        .order_by(TicketEvent.created_at.asc())
        .all()
    )

    return templates.TemplateResponse(
        "ticket_detail.html",
        {
            "request": request,
            "ticket": ticket,
            "events": events,
        }
    )


@router.post("/tickets/{ticket_no}/status-form")
async def update_status_form(
    request: Request,
    ticket_no: str,
    db: Session = Depends(get_db),
):
    form = await parse_form_data(request)
    try:
        update_ticket_status(
            db, ticket_no,
            status=form.get("status", "PROCESSING"),
            operator_account=form.get("operator_account", ""),
            operator_name=form.get("operator_name", ""),
            comment=form.get("comment", ""),
        )
    except ValueError as e:
        status_code = 404 if "不存在" in str(e) else 400
        raise HTTPException(status_code=status_code, detail=str(e))
    return redirect_to_ticket_actions(ticket_no)


@router.post("/tickets/{ticket_no}/comment-form")
async def add_comment_form(
    request: Request,
    ticket_no: str,
    db: Session = Depends(get_db),
):
    form = await parse_form_data(request)
    add_comment(
        db, ticket_no,
        operator_account=form.get("operator_account", ""),
        operator_name=form.get("operator_name", ""),
        comment=form.get("comment", ""),
    )
    return redirect_to_ticket_actions(ticket_no)


@router.post("/tickets/{ticket_no}/close-form")
async def close_ticket_form(
    request: Request,
    ticket_no: str,
    db: Session = Depends(get_db),
):
    form = await parse_form_data(request)
    close_ticket(
        db, ticket_no,
        operator_account=form.get("operator_account", ""),
        operator_name=form.get("operator_name", ""),
        resolved_result=form.get("resolved_result", ""),
    )
    return redirect_to_ticket_actions(ticket_no)
