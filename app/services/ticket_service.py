import hashlib
from datetime import datetime
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Ticket, TicketEvent
from app.schemas import CreateTicketRequest
from app.services.id_generator import generate_ticket_no


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

    ticket_no = generate_ticket_no(db)
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
    db.flush()

    event = TicketEvent(
        ticket_no=ticket.ticket_no,
        event_type="CREATED",
        to_status="NEW",
        operator_account="SYSTEM",
        operator_name="系统",
        event_content="Dify 诊断智能体自动创建工单"
    )
    db.add(event)

    db.commit()
    db.refresh(ticket)

    return ticket, False


def update_ticket_status(
    db: Session,
    ticket_no: str,
    status: str,
    operator_account: str = "",
    operator_name: str = "",
    comment: str = "",
) -> Ticket:
    ticket = db.query(Ticket).filter(Ticket.ticket_no == ticket_no).first()
    if not ticket:
        raise ValueError("工单不存在")

    old_status = ticket.status
    ticket.status = status

    if status == "RESOLVED":
        ticket.resolved_at = datetime.utcnow()

    event = TicketEvent(
        ticket_no=ticket_no,
        event_type="STATUS_CHANGED",
        from_status=old_status,
        to_status=status,
        operator_account=operator_account,
        operator_name=operator_name,
        event_content=comment or f"状态从 {old_status} 变更为 {status}"
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
