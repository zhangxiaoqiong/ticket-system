from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Ticket, TicketEvent
from app.schemas import (
    CreateTicketRequest,
    ApiResponse,
    CreateTicketResponseData,
    UpdateStatusRequest,
    AddCommentRequest,
    CloseTicketRequest,
)
from app.services.ticket_service import (
    create_ticket,
    update_ticket_status,
    add_comment,
    close_ticket,
)
from app.services.notify_service import notify_group

router = APIRouter(prefix="/api/tickets", tags=["tickets"])


@router.post("", response_model=ApiResponse)
async def create_ticket_api(req: CreateTicketRequest, db: Session = Depends(get_db)):
    try:
        ticket, duplicated = create_ticket(db, req)

        if not duplicated:
            await notify_group(db, ticket)

        return ApiResponse(
            success=True,
            code="0",
            message="工单已存在" if duplicated else "工单创建成功",
            data=CreateTicketResponseData(
                ticketNo=ticket.ticket_no,
                ticketUrl=ticket.ticket_url,
                status=ticket.status,
                duplicated=duplicated,
            )
        )

    except Exception as e:
        return ApiResponse(
            success=False,
            code="500",
            message=f"工单创建失败：{str(e)}",
            data=None
        )


@router.get("")
def list_tickets(
    status: str | None = None,
    priority: str | None = None,
    reporterAccount: str | None = None,
    ownerKey: str | None = None,
    ticketNo: str | None = None,
    keyword: str | None = None,
    pageNo: int = Query(1, ge=1),
    pageSize: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    query = db.query(Ticket)

    if status:
        query = query.filter(Ticket.status == status)
    if priority:
        query = query.filter(Ticket.priority == priority)
    if reporterAccount:
        query = query.filter(Ticket.reporter_account == reporterAccount)
    if ownerKey:
        query = query.filter(Ticket.owner_key == ownerKey)
    if ticketNo:
        query = query.filter(Ticket.ticket_no == ticketNo)
    if keyword:
        like = f"%{keyword}%"
        query = query.filter(
            Ticket.full_address.like(like)
            | Ticket.user_query.like(like)
            | Ticket.issue_type.like(like)
        )

    total = query.count()
    rows = (
        query.order_by(Ticket.created_at.desc())
        .offset((pageNo - 1) * pageSize)
        .limit(pageSize)
        .all()
    )

    return {
        "success": True,
        "total": total,
        "pageNo": pageNo,
        "pageSize": pageSize,
        "data": rows,
    }


@router.get("/{ticket_no}")
def get_ticket_detail(ticket_no: str, db: Session = Depends(get_db)):
    ticket = db.query(Ticket).filter(Ticket.ticket_no == ticket_no).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="工单不存在")

    events = (
        db.query(TicketEvent)
        .filter(TicketEvent.ticket_no == ticket_no)
        .order_by(TicketEvent.created_at.asc())
        .all()
    )

    return {
        "success": True,
        "data": {
            "ticket": ticket,
            "events": events,
        }
    }


@router.post("/{ticket_no}/status")
def update_status_api(ticket_no: str, req: UpdateStatusRequest, db: Session = Depends(get_db)):
    try:
        ticket = update_ticket_status(
            db=db,
            ticket_no=ticket_no,
            status=req.status,
            operator_account=req.operatorAccount or "",
            operator_name=req.operatorName or "",
            comment=req.comment or "",
        )
        return {"success": True, "data": ticket}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{ticket_no}/comments")
def add_comment_api(ticket_no: str, req: AddCommentRequest, db: Session = Depends(get_db)):
    try:
        add_comment(
            db=db,
            ticket_no=ticket_no,
            operator_account=req.operatorAccount or "",
            operator_name=req.operatorName or "",
            comment=req.comment,
        )
        return {"success": True, "message": "备注添加成功"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{ticket_no}/close")
def close_ticket_api(ticket_no: str, req: CloseTicketRequest, db: Session = Depends(get_db)):
    try:
        ticket = close_ticket(
            db=db,
            ticket_no=ticket_no,
            operator_account=req.operatorAccount or "",
            operator_name=req.operatorName or "",
            resolved_result=req.resolvedResult,
        )
        return {"success": True, "data": ticket}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
