import hashlib
from datetime import datetime
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Ticket, TicketEvent
from app.schemas import CreateTicketRequest
from app.services.id_generator import generate_ticket_no

ALLOWED_STATUSES = {"NEW", "PROCESSING", "RESOLVED", "CLOSED"}
EDITABLE_STATUSES = {"NEW", "PROCESSING", "RESOLVED"}


def clean(value) -> str:
    return str(value or "").strip()


def build_owner_key(req: CreateTicketRequest) -> str:
    return (
        clean(req.reporterAccount)
        or clean(req.channelUserId)
        or clean(req.sessionId)
        or "UNKNOWN_USER"
    )


def build_idempotent_key(req: CreateTicketRequest, owner_key: str) -> str:
    if req.idempotentKey:
        return clean(req.idempotentKey)

    raw = "|".join([
        clean(req.sourceChannel),
        clean(req.businessType),
        owner_key,
        clean(req.fullAddress),
        clean(req.expectedResult),
        clean(req.issueType),
        clean(req.waybillNo),
    ])

    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def create_ticket(db: Session, req: CreateTicketRequest) -> tuple[Ticket, bool]:
    owner_key = build_owner_key(req)
    idempotent_key = build_idempotent_key(req, owner_key)

    existing = (
        db.query(Ticket)
        .filter(Ticket.idempotent_key == idempotent_key)
        .first()
    )

    if existing:
        return existing, True

    requested_ticket_no = clean(req.ticketNo)
    max_attempts = 1 if requested_ticket_no else 5

    for _ in range(max_attempts):
        ticket_no = requested_ticket_no or generate_ticket_no(db)
        ticket_url = f"{settings.base_url}/tickets/{ticket_no}"

        ticket = Ticket(
            ticket_no=ticket_no,
            source_channel=req.sourceChannel,
            business_type=req.businessType,

            status="NEW",
            priority=req.priority or "P3",
            severity_type=req.severityType,
            issue_type=req.issueType,

            reporter_account=req.reporterAccount,
            reporter_name=req.reporterName,
            channel_user_id=req.channelUserId,
            session_id=req.sessionId,
            owner_key=owner_key,

            user_query=req.userQuery,
            full_address=req.fullAddress,
            expected_result=req.expectedResult,
            waybill_no=req.waybillNo,

            diagnosis_summary=req.diagnosisSummary,
            internal_suggestion=req.internalSuggestion,
            customer_reply_type=req.customerReplyType,

            diagnosis_payload=req.diagnosisPayload or {},
            idempotent_key=idempotent_key,
            ticket_url=ticket_url,
        )

        db.add(ticket)

        event = TicketEvent(
            ticket_no=ticket.ticket_no,
            event_type="CREATED",
            to_status="NEW",
            operator_account="SYSTEM",
            operator_name="系统",
            event_content="Dify 诊断智能体自动创建工单"
        )
        db.add(event)

        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            existing = (
                db.query(Ticket)
                .filter(Ticket.idempotent_key == idempotent_key)
                .first()
            )
            if existing:
                return existing, True
            if requested_ticket_no:
                raise ValueError(f"工单号已存在：{requested_ticket_no}")
            continue

        db.refresh(ticket)
        return ticket, False

    raise RuntimeError("工单号生成冲突，请稍后重试")


def update_ticket_status(
    db: Session,
    ticket_no: str,
    status: str,
    operator_account: str = "",
    operator_name: str = "",
    comment: str = "",
) -> Ticket:
    if status not in ALLOWED_STATUSES:
        raise ValueError(f"非法状态：{status}")

    ticket = db.query(Ticket).filter(Ticket.ticket_no == ticket_no).first()
    if not ticket:
        raise ValueError("工单不存在")

    old_status = ticket.status
    if old_status == "CLOSED":
        raise ValueError("工单已关闭，不能再更新状态")
    if status == "CLOSED":
        raise ValueError("请通过关闭工单操作关闭")
    if status not in EDITABLE_STATUSES:
        raise ValueError(f"非法状态：{status}")

    ticket.status = status
    operator_display = clean(operator_name) or clean(operator_account)
    if operator_display:
        ticket.assigned_operator = operator_display

    if status == "RESOLVED":
        ticket.resolved_at = datetime.utcnow()
    elif old_status == "RESOLVED":
        ticket.resolved_at = None

    event = TicketEvent(
        ticket_no=ticket_no,
        event_type="STATUS_CHANGED" if status != old_status else "STATUS_REMARKED",
        from_status=old_status,
        to_status=status,
        operator_account=operator_account,
        operator_name=operator_name,
        event_content=comment or (
            f"状态从 {old_status} 变更为 {status}"
            if status != old_status
            else f"{status} 状态下补充处理记录"
        )
    )
    db.add(event)
    db.commit()
    db.refresh(ticket)

    return ticket


def add_comment(
    db: Session,
    ticket_no: str,
    operator_account: str,
    operator_name: str,
    comment: str,
) -> None:
    ticket = db.query(Ticket).filter(Ticket.ticket_no == ticket_no).first()
    if not ticket:
        raise ValueError("工单不存在")

    event = TicketEvent(
        ticket_no=ticket_no,
        event_type="COMMENT_ADDED",
        operator_account=operator_account,
        operator_name=operator_name,
        event_content=comment,
    )
    db.add(event)
    db.commit()


def close_ticket(
    db: Session,
    ticket_no: str,
    operator_account: str,
    operator_name: str,
    resolved_result: str,
) -> Ticket:
    ticket = db.query(Ticket).filter(Ticket.ticket_no == ticket_no).first()
    if not ticket:
        raise ValueError("工单不存在")

    old_status = ticket.status
    ticket.status = "CLOSED"
    ticket.resolved_result = resolved_result
    operator_display = clean(operator_name) or clean(operator_account)
    if operator_display:
        ticket.assigned_operator = operator_display
    ticket.closed_at = datetime.utcnow()

    event = TicketEvent(
        ticket_no=ticket_no,
        event_type="CLOSED",
        from_status=old_status,
        to_status="CLOSED",
        operator_account=operator_account,
        operator_name=operator_name,
        event_content=resolved_result,
    )

    db.add(event)
    db.commit()
    db.refresh(ticket)

    return ticket
