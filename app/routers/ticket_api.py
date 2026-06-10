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
    UpdateTicketItemRequest,
    BatchUpdateTicketItemsRequest,
)
from app.services.ticket_service import (
    create_ticket,
    update_ticket_status,
    add_comment,
    close_ticket,
    count_ticket_items,
    list_ticket_items,
    update_ticket_item_status,
    batch_update_ticket_item_status,
)
from app.services.notify_service import notify_group, notify_ticket_items_processed

router = APIRouter(prefix="/api/tickets", tags=["tickets"])


def ticket_item_payload(item):
    return {
        "id": item.id,
        "ticketNo": item.ticket_no,
        "itemKey": item.item_key,
        "itemNo": item.item_no,
        "status": item.status,
        "fullAddress": item.full_address,
        "issueDescription": item.issue_description,
        "replyDesc": item.reply_desc,
        "operatorAccount": item.operator_account,
        "operatorName": item.operator_name,
        "processedAt": item.processed_at,
    }


@router.post("", response_model=ApiResponse)
async def create_ticket_api(req: CreateTicketRequest, db: Session = Depends(get_db)):
    try:
        ticket, duplicated = create_ticket(db, req)

        if not duplicated:
            try:
                await notify_group(db, ticket)
            except Exception as notify_error:
                db.rollback()
                event = TicketEvent(
                    ticket_no=ticket.ticket_no,
                    event_type="NOTIFY_FAILED",
                    event_content=f"工单已创建，但消息通知失败：{str(notify_error)}",
                )
                db.add(event)
                db.commit()

        return ApiResponse(
            success=True,
            code="0",
            message="工单已存在" if duplicated else "工单创建成功",
            data=CreateTicketResponseData(
                ticketNo=ticket.ticket_no,
                ticketUrl=ticket.ticket_url,
                status=ticket.status,
                duplicated=duplicated,
                itemCount=count_ticket_items(db, ticket.ticket_no),
            )
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"工单创建失败：{str(e)}")


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
            "items": list_ticket_items(db, ticket_no),
            "events": events,
        }
    }


@router.post("/{ticket_no}/items/{item_id}/status")
async def update_item_status_api(
    ticket_no: str,
    item_id: int,
    req: UpdateTicketItemRequest,
    db: Session = Depends(get_db),
):
    try:
        item = update_ticket_item_status(
            db=db,
            ticket_no=ticket_no,
            item_id=item_id,
            status=req.status,
            reply_desc=req.replyDesc or "",
            operator_account=req.operatorAccount or "",
            operator_name=req.operatorName or "",
        )
        await notify_ticket_items_processed(
            db,
            ticket_no=ticket_no,
            items=[item],
            operator_account=req.operatorAccount or "",
            operator_name=req.operatorName or "",
            reply_desc=req.replyDesc or "",
        )
        return {"success": True, "data": ticket_item_payload(item)}
    except ValueError as e:
        status_code = 404 if "not found" in str(e) else 400
        raise HTTPException(status_code=status_code, detail=str(e))


@router.post("/{ticket_no}/items/batch-status")
async def batch_update_item_status_api(
    ticket_no: str,
    req: BatchUpdateTicketItemsRequest,
    db: Session = Depends(get_db),
):
    try:
        items = batch_update_ticket_item_status(
            db=db,
            ticket_no=ticket_no,
            item_ids=req.itemIds,
            status=req.status,
            reply_desc=req.replyDesc or "",
            operator_account=req.operatorAccount or "",
            operator_name=req.operatorName or "",
        )
        await notify_ticket_items_processed(
            db,
            ticket_no=ticket_no,
            items=items,
            operator_account=req.operatorAccount or "",
            operator_name=req.operatorName or "",
            reply_desc=req.replyDesc or "",
        )
        return {"success": True, "data": [ticket_item_payload(item) for item in items]}
    except ValueError as e:
        status_code = 404 if "not found" in str(e) else 400
        raise HTTPException(status_code=status_code, detail=str(e))


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
        status_code = 404 if "不存在" in str(e) else 400
        raise HTTPException(status_code=status_code, detail=str(e))


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
