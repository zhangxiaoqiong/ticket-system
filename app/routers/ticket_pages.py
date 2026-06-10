import json
from urllib.parse import parse_qs, quote, urlencode, unquote

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Ticket, TicketEvent
from app.services.notify_service import notify_ticket_items_processed
from app.services.ticket_service import (
    update_ticket_status,
    add_comment,
    close_ticket,
    list_ticket_items,
    update_ticket_item_status,
    batch_update_ticket_item_status,
)

router = APIRouter(tags=["pages"])
templates = Jinja2Templates(directory="app/templates")


def pretty_json(value) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)


templates.env.filters["pretty_json"] = pretty_json


def status_text(value: str) -> str:
    return {
        "NEW": "待处理",
        "PROCESSING": "处理中",
        "RESOLVED": "已处理",
        "CLOSED": "已处理",
    }.get(value or "", value or "-")


templates.env.filters["status_text"] = status_text


def event_type_text(value: str) -> str:
    return {
        "CREATED": "工单创建",
        "STATUS_CHANGED": "工单状态变更",
        "STATUS_REMARKED": "工单状态备注",
        "STATUS_AGGREGATED": "工单状态汇总",
        "ITEM_STATUS_CHANGED": "地址状态变更",
        "ITEM_STATUS_REMARKED": "地址处理备注",
        "COMMENT_ADDED": "添加备注",
        "CLOSED": "工单关闭",
        "BOT_NOTIFIED": "机器人通知已发送",
        "BOT_ITEMS_PROCESSED_NOTIFIED": "处理结果通知已发送",
        "NOTIFY_FAILED": "机器人通知失败",
        "BOT_ITEMS_PROCESSED_NOTIFY_FAILED": "处理结果通知失败",
        "FS_NEXT_NOTIFIED": "旧通知已发送",
        "FS_NEXT_NOTIFY_FAILED": "旧通知失败",
        "FS_NEXT_NOTIFY_SKIPPED": "旧通知跳过",
    }.get(value or "", value or "-")


def event_content_text(value: str) -> str:
    text = value or ""
    for raw in ("PROCESSING", "RESOLVED", "CLOSED", "NEW"):
        text = text.replace(raw, status_text(raw))
    return (
        text.replace("status updated", "状态已更新")
        .replace("Ticket status aggregated from address item statuses", "已根据地址明细状态汇总工单状态")
        .replace("Dify diagnosis agent created ticket", "智能诊断助手创建工单")
        .replace("robot message sent", "机器人消息已发送")
        .replace("response=", "返回=")
        .replace("status=", "状态码=")
    )


templates.env.filters["event_type_text"] = event_type_text
templates.env.filters["event_content_text"] = event_content_text

OPERATOR_ACCOUNT_COOKIE = "ticket_operator_account"
OPERATOR_NAME_COOKIE = "ticket_operator_name"


def current_operator(request: Request) -> dict[str, str] | None:
    account = (request.cookies.get(OPERATOR_ACCOUNT_COOKIE) or "").strip()
    if not account:
        return None
    return {
        "account": account,
        "name": unquote(request.cookies.get(OPERATOR_NAME_COOKIE) or "").strip(),
    }


def redirect_to_login(request: Request) -> RedirectResponse:
    next_url = str(request.url)
    return RedirectResponse(
        url=str(request.url_for("operator_login")) + f"?next={quote(next_url, safe='')}",
        status_code=302,
    )


def operator_or_redirect(request: Request) -> dict[str, str] | RedirectResponse:
    operator = current_operator(request)
    if operator:
        return operator
    return redirect_to_login(request)


def redirect_to_ticket_actions(request: Request, ticket_no: str) -> RedirectResponse:
    return RedirectResponse(
        url=str(request.url_for("ticket_detail", ticket_no=ticket_no)) + "#actions",
        status_code=302,
    )


async def parse_form_data(request: Request) -> dict:
    body = (await request.body()).decode("utf-8")
    parsed = parse_qs(body, keep_blank_values=True)
    return {key: values[-1] if values else "" for key, values in parsed.items()}


@router.get("/login", name="operator_login")
def operator_login_page(request: Request, next: str | None = None):
    operator = current_operator(request)
    if operator:
        return RedirectResponse(url=next or str(request.url_for("ticket_list")), status_code=302)
    return templates.TemplateResponse(
        request,
        "login.html",
        {
            "request": request,
            "next": next or str(request.url_for("ticket_list")),
            "error": "",
        },
    )


@router.post("/login")
async def operator_login(request: Request):
    form = await parse_form_data(request)
    account = (form.get("operator_account") or "").strip()
    name = (form.get("operator_name") or "").strip()
    next_url = form.get("next") or str(request.url_for("ticket_list"))
    if not account:
        return templates.TemplateResponse(
            request,
            "login.html",
            {
                "request": request,
                "next": next_url,
                "error": "请填写运营处理人工号",
            },
            status_code=400,
        )

    response = RedirectResponse(url=next_url, status_code=302)
    response.set_cookie(OPERATOR_ACCOUNT_COOKIE, account, max_age=7 * 24 * 3600, httponly=True, samesite="lax")
    response.set_cookie(OPERATOR_NAME_COOKIE, quote(name), max_age=7 * 24 * 3600, httponly=True, samesite="lax")
    return response


@router.get("/logout")
def operator_logout(request: Request):
    response = RedirectResponse(url=str(request.url_for("operator_login")), status_code=302)
    response.delete_cookie(OPERATOR_ACCOUNT_COOKIE)
    response.delete_cookie(OPERATOR_NAME_COOKIE)
    return response


@router.get("/tickets")
def ticket_list(
    request: Request,
    status: str | None = None,
    keyword: str | None = None,
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
):
    operator = operator_or_redirect(request)
    if isinstance(operator, RedirectResponse):
        return operator

    query = db.query(Ticket)
    status = (status or "").strip()
    keyword = (keyword or "").strip()
    page = max(page, 1)
    page_size = page_size if page_size in {10, 20, 50, 100} else 20

    if status == "RESOLVED":
        query = query.filter(Ticket.status.in_(["RESOLVED", "CLOSED"]))
    elif status:
        query = query.filter(Ticket.status == status)

    if keyword:
        like = f"%{keyword}%"
        query = query.filter(
            Ticket.ticket_no.like(like)
            | Ticket.full_address.like(like)
            | Ticket.user_query.like(like)
            | Ticket.issue_type.like(like)
            | Ticket.reporter_group.like(like)
            | Ticket.reporter_account.like(like)
            | Ticket.channel_user_id.like(like)
        )

    total = query.count()
    total_pages = max((total + page_size - 1) // page_size, 1)
    page = min(page, total_pages)
    tickets = (
        query.order_by(Ticket.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    encoded_filters = urlencode({
        key: value
        for key, value in {
            "status": status,
            "keyword": keyword,
            "page_size": page_size,
        }.items()
        if value not in ("", None)
    })
    query_suffix = f"&{encoded_filters}" if encoded_filters else ""

    return templates.TemplateResponse(
        request,
        "ticket_list.html",
        {
            "request": request,
            "tickets": tickets,
            "status": status,
            "keyword": keyword,
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": total_pages,
            "query_suffix": query_suffix,
            "operator": operator,
        }
    )


@router.get("/tickets/{ticket_no}")
def ticket_detail(request: Request, ticket_no: str, db: Session = Depends(get_db)):
    operator = operator_or_redirect(request)
    if isinstance(operator, RedirectResponse):
        return operator

    ticket = db.query(Ticket).filter(Ticket.ticket_no == ticket_no).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="工单不存在")

    events = (
        db.query(TicketEvent)
        .filter(TicketEvent.ticket_no == ticket_no)
        .order_by(TicketEvent.created_at.asc())
        .all()
    )
    items = list_ticket_items(db, ticket_no)

    return templates.TemplateResponse(
        request,
        "ticket_detail.html",
        {
            "request": request,
            "ticket": ticket,
            "items": items,
            "events": events,
            "operator": operator,
        }
    )


@router.post("/tickets/{ticket_no}/status-form")
async def update_status_form(
    request: Request,
    ticket_no: str,
    db: Session = Depends(get_db),
):
    operator = operator_or_redirect(request)
    if isinstance(operator, RedirectResponse):
        return operator

    form = await parse_form_data(request)
    try:
        update_ticket_status(
            db, ticket_no,
            status=form.get("status", "PROCESSING"),
            operator_account=operator["account"],
            operator_name=operator["name"],
            comment=form.get("comment", ""),
        )
    except ValueError as e:
        status_code = 404 if "不存在" in str(e) else 400
        raise HTTPException(status_code=status_code, detail=str(e))
    return redirect_to_ticket_actions(request, ticket_no)


@router.post("/tickets/{ticket_no}/items/{item_id}/status-form")
async def update_item_status_form(
    request: Request,
    ticket_no: str,
    item_id: int,
    db: Session = Depends(get_db),
):
    operator = operator_or_redirect(request)
    if isinstance(operator, RedirectResponse):
        return operator

    form = await parse_form_data(request)
    try:
        item = update_ticket_item_status(
            db=db,
            ticket_no=ticket_no,
            item_id=item_id,
            status=form.get("status", "RESOLVED"),
            reply_desc=form.get("reply_desc", ""),
            operator_account=operator["account"],
            operator_name=operator["name"],
        )
        await notify_ticket_items_processed(
            db,
            ticket_no=ticket_no,
            items=[item],
            operator_account=operator["account"],
            operator_name=operator["name"],
            reply_desc=form.get("reply_desc", ""),
        )
    except ValueError as e:
        status_code = 404 if "not found" in str(e) else 400
        raise HTTPException(status_code=status_code, detail=str(e))
    return redirect_to_ticket_actions(request, ticket_no)


@router.post("/tickets/{ticket_no}/items/batch-status-form")
async def batch_update_item_status_form(
    request: Request,
    ticket_no: str,
    db: Session = Depends(get_db),
):
    operator = operator_or_redirect(request)
    if isinstance(operator, RedirectResponse):
        return operator

    form = await parse_form_data(request)
    item_ids = [
        int(item_id)
        for item_id in form.get("item_ids", "").split(",")
        if item_id.strip().isdigit()
    ]
    if not item_ids:
        raise HTTPException(status_code=400, detail="please select at least one item")

    try:
        items = batch_update_ticket_item_status(
            db=db,
            ticket_no=ticket_no,
            item_ids=item_ids,
            status=form.get("status", "RESOLVED"),
            reply_desc=form.get("reply_desc", ""),
            operator_account=operator["account"],
            operator_name=operator["name"],
        )
        await notify_ticket_items_processed(
            db,
            ticket_no=ticket_no,
            items=items,
            operator_account=operator["account"],
            operator_name=operator["name"],
            reply_desc=form.get("reply_desc", ""),
        )
    except ValueError as e:
        status_code = 404 if "not found" in str(e) else 400
        raise HTTPException(status_code=status_code, detail=str(e))
    return redirect_to_ticket_actions(request, ticket_no)


@router.post("/tickets/{ticket_no}/comment-form")
async def add_comment_form(
    request: Request,
    ticket_no: str,
    db: Session = Depends(get_db),
):
    operator = operator_or_redirect(request)
    if isinstance(operator, RedirectResponse):
        return operator

    form = await parse_form_data(request)
    add_comment(
        db, ticket_no,
        operator_account=operator["account"],
        operator_name=operator["name"],
        comment=form.get("comment", ""),
    )
    return redirect_to_ticket_actions(request, ticket_no)


@router.post("/tickets/{ticket_no}/close-form")
async def close_ticket_form(
    request: Request,
    ticket_no: str,
    db: Session = Depends(get_db),
):
    operator = operator_or_redirect(request)
    if isinstance(operator, RedirectResponse):
        return operator

    form = await parse_form_data(request)
    close_ticket(
        db, ticket_no,
        operator_account=operator["account"],
        operator_name=operator["name"],
        resolved_result=form.get("resolved_result", ""),
    )
    return redirect_to_ticket_actions(request, ticket_no)
