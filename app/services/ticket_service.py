import hashlib
import json
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Ticket, TicketEvent, TicketItem, local_now
from app.schemas import CreateTicketRequest
from app.services.id_generator import generate_ticket_no

ALLOWED_STATUSES = {"NEW", "PROCESSING", "RESOLVED", "CLOSED"}


def clean(value) -> str:
    return str(value or "").strip()


def request_to_dict(req: CreateTicketRequest) -> dict[str, Any]:
    if hasattr(req, "model_dump"):
        return req.model_dump()
    return req.dict()


def first_value(data: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        value = data.get(key)
        if value not in (None, ""):
            return value
    return default


def parse_json_object(value: Any) -> dict[str, Any]:
    if not value:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        parsed = json.loads(value)
        if isinstance(parsed, dict):
            return parsed
    raise ValueError("ticket_payload must be a JSON object or JSON object string")


def normalize_notify_user_ids(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [clean(item) for item in value if clean(item)]
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return [clean(value)]


def normalize_create_payload(req: CreateTicketRequest) -> dict[str, Any]:
    raw = request_to_dict(req)
    embedded_payload = first_value(raw, "ticket_payload", "ticketPayload")

    if embedded_payload:
        payload = parse_json_object(embedded_payload)
        outer = raw
    else:
        payload = dict(raw)
        outer = raw

    if first_value(payload, "batch_items") and not first_value(payload, "items"):
        payload["items"] = payload.get("batch_items")
    if first_value(outer, "batch_items") and not first_value(payload, "items"):
        payload["items"] = outer.get("batch_items")

    field_pairs = [
        ("ticketNo", ("ticketNo",)),
        ("ticketMode", ("ticketMode", "ticket_mode", "ticket_type")),
        ("sourceChannel", ("sourceChannel",)),
        ("businessType", ("businessType",)),
        ("reporterAccount", ("reporterAccount", "reporter_account", "owner_key")),
        ("actualReporterAccount", ("actualReporterAccount", "actual_reporter_account")),
        ("reporterName", ("reporterName",)),
        ("reporterGroup", ("reporterGroup", "reporter_group")),
        ("reporterGroupName", ("reporterGroupName", "reporter_group_name")),
        ("notifyUserIds", ("notifyUserIds",)),
        ("channelUserId", ("channelUserId", "channel_user_id")),
        ("sessionId", ("sessionId", "session_id")),
        ("userQuery", ("userQuery", "user_query")),
        ("idempotentKey", ("idempotentKey", "idempotent_key")),
        ("priority", ("priority", "batch_priority")),
        ("severityType", ("severityType", "severity_type", "batch_severity_type")),
        ("summary", ("summary", "batch_diagnosis_summary", "diagnosis_summary")),
        ("customerReplyType", ("customerReplyType", "customer_reply_type")),
    ]
    for target, keys in field_pairs:
        if not first_value(payload, target):
            value = first_value(outer, *keys)
            if value not in (None, ""):
                payload[target] = value

    if not payload.get("ticketMode"):
        payload["ticketMode"] = "batch" if payload.get("items") else "single"
    if not payload.get("sourceChannel"):
        payload["sourceChannel"] = "DIFY_ADDRESS_DIAGNOSIS_AGENT"
    if not payload.get("businessType"):
        payload["businessType"] = "SXFD_DIAGNOSIS"

    payload["notifyUserIds"] = normalize_notify_user_ids(payload.get("notifyUserIds"))

    items = payload.get("items") or []
    if not isinstance(items, list):
        raise ValueError("items must be a list")
    if not items:
        items = [legacy_item_from_payload(payload)]
    payload["items"] = [normalize_item(item, index) for index, item in enumerate(items, start=1)]
    return payload


def legacy_item_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    diagnosis_payload = payload.get("diagnosisPayload") or {}
    return {
        "itemKey": "addr_001",
        "fullAddress": first_value(payload, "fullAddress"),
        "waybillNo": first_value(payload, "waybillNo"),
        "userQuery": first_value(payload, "userQuery"),
        "issueDescription": first_value(payload, "issueDescription", "userQuery"),
        "expectedResult": first_value(payload, "expectedResult"),
        "issueType": first_value(payload, "issueType"),
        "priority": first_value(payload, "priority"),
        "severityType": first_value(payload, "severityType"),
        "diagnosisSummary": first_value(payload, "diagnosisSummary", "summary"),
        "diagnosisText": first_value(payload, "diagnosisText", "diagnosisSummary", "summary"),
        "customerReplyReference": first_value(payload, "customerReplyReference"),
        "operationSuggestion": first_value(payload, "operationSuggestion"),
        "v5Result": first_value(diagnosis_payload.get("apiContext") or {}, "v5Result", default={}),
        "villageResult": first_value(diagnosis_payload.get("apiContext") or {}, "villageResult", "villageDiagnosisResult", default={}),
        "diagnosisPayload": diagnosis_payload,
        "notifyUserIds": first_value(payload, "notifyUserIds", default=[]),
    }


def normalize_item(item: dict[str, Any], index: int) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise ValueError("each item must be a JSON object")

    diagnosis_payload = item.get("diagnosisPayload") or {}
    item_input = diagnosis_payload.get("itemInput") or {}
    api_context = diagnosis_payload.get("apiContext") or {}
    operation_sop = diagnosis_payload.get("operationSop") or {}

    operation_suggestion = first_value(
        item,
        "operationSuggestion",
        default=operation_sop.get("operationSuggestion") or operation_sop.get("detailSuggestion") or {},
    )

    return {
        "itemKey": clean(first_value(item, "itemKey", default=item_input.get("itemKey") or f"addr_{index:03d}")),
        "itemNo": int(first_value(item, "itemNo", default=item_input.get("itemNo") or index)),
        "fullAddress": first_value(item, "fullAddress", default=item_input.get("fullAddress")),
        "waybillNo": first_value(item, "waybillNo", default=item_input.get("waybillNo")),
        "userQuery": first_value(item, "userQuery", default=item_input.get("userQuery")),
        "issueDescription": first_value(item, "issueDescription", default=item_input.get("problemDesc")),
        "expectedResult": first_value(item, "expectedResult", default=item_input.get("expectedResult")),
        "issueType": first_value(item, "issueType", default=item_input.get("problemType")),
        "priority": first_value(item, "priority", default="P3"),
        "severityType": first_value(item, "severityType"),
        "diagnosisSummary": first_value(item, "diagnosisSummary"),
        "diagnosisText": first_value(item, "diagnosisText", "diagnosisSummary"),
        "customerReplyReference": first_value(
            item,
            "customerReplyReference",
            default=operation_sop.get("customerReplyReference"),
        ),
        "operationSuggestion": operation_suggestion or {},
        "v5Result": first_value(item, "v5Result", default=api_context.get("v5Result") or {}),
        "villageResult": first_value(
            item,
            "villageResult",
            default=api_context.get("villageResult") or api_context.get("villageDiagnosisResult") or {},
        ),
        "diagnosisPayload": diagnosis_payload,
        "notifyUserIds": normalize_notify_user_ids(item.get("notifyUserIds")),
        "processStatus": first_value(item, "processStatus", default="NEW"),
        "replyDesc": first_value(item, "replyDesc", default=""),
    }


def build_owner_key_from_payload(payload: dict[str, Any]) -> str:
    return (
        clean(payload.get("reporterAccount"))
        or clean(payload.get("channelUserId"))
        or clean(payload.get("sessionId"))
        or "UNKNOWN_USER"
    )


def build_idempotent_key_from_payload(payload: dict[str, Any], owner_key: str) -> str:
    if payload.get("idempotentKey"):
        return clean(payload.get("idempotentKey"))

    raw = "|".join([
        clean(payload.get("sourceChannel")),
        clean(payload.get("businessType")),
        owner_key,
        clean(payload.get("userQuery")),
        "|".join(clean(item.get("fullAddress")) for item in payload["items"]),
    ])
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def ticket_payload_snapshot(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in payload.items()
        if key != "items"
    } | {
        "itemCount": len(payload.get("items") or []),
    }


def create_ticket_item(ticket_no: str, item: dict[str, Any]) -> TicketItem:
    return TicketItem(
        ticket_no=ticket_no,
        item_key=item["itemKey"],
        item_no=item["itemNo"],
        status="NEW",
        priority=item.get("priority") or "P3",
        severity_type=item.get("severityType"),
        issue_type=item.get("issueType"),
        full_address=item.get("fullAddress"),
        user_query=item.get("userQuery"),
        issue_description=item.get("issueDescription"),
        expected_result=item.get("expectedResult"),
        waybill_no=item.get("waybillNo"),
        diagnosis_summary=item.get("diagnosisSummary"),
        diagnosis_text=item.get("diagnosisText"),
        customer_reply_reference=item.get("customerReplyReference"),
        operation_suggestion=item.get("operationSuggestion") or {},
        v5_result=item.get("v5Result") or {},
        village_result=item.get("villageResult") or {},
        diagnosis_payload=item.get("diagnosisPayload") or {},
        notify_user_ids=item.get("notifyUserIds") or [],
        reply_desc=item.get("replyDesc") or "",
    )


def create_ticket(db: Session, req: CreateTicketRequest) -> tuple[Ticket, bool]:
    payload = normalize_create_payload(req)
    owner_key = build_owner_key_from_payload(payload)
    idempotent_key = build_idempotent_key_from_payload(payload, owner_key)

    existing = (
        db.query(Ticket)
        .filter(Ticket.idempotent_key == idempotent_key)
        .first()
    )
    if existing:
        return existing, True

    requested_ticket_no = clean(payload.get("ticketNo"))
    max_attempts = 1 if requested_ticket_no else 5
    first_item = payload["items"][0]

    for _ in range(max_attempts):
        ticket_no = requested_ticket_no or generate_ticket_no(db)
        ticket_url = f"{settings.base_url}/tickets/{ticket_no}"
        is_batch = len(payload["items"]) > 1 or payload.get("ticketMode") == "batch"

        ticket = Ticket(
            ticket_no=ticket_no,
            source_channel=payload.get("sourceChannel"),
            business_type=payload.get("businessType"),
            status="NEW",
            priority=payload.get("priority") or first_item.get("priority") or "P3",
            severity_type=payload.get("severityType") or first_item.get("severityType"),
            issue_type=first_item.get("issueType"),
            reporter_account=payload.get("reporterAccount"),
            actual_reporter_account=payload.get("actualReporterAccount"),
            reporter_name=payload.get("reporterName"),
            reporter_group=payload.get("reporterGroup"),
            reporter_group_name=payload.get("reporterGroupName"),
            channel_user_id=payload.get("channelUserId"),
            session_id=payload.get("sessionId"),
            owner_key=owner_key,
            user_query=payload.get("userQuery"),
            full_address=payload.get("batch_full_address_text") or first_item.get("fullAddress"),
            expected_result=first_item.get("expectedResult"),
            waybill_no=first_item.get("waybillNo"),
            diagnosis_summary=payload.get("summary") or first_item.get("diagnosisSummary"),
            internal_suggestion=(first_item.get("operationSuggestion") or {}).get("suggestion"),
            customer_reply_type=payload.get("customerReplyType"),
            diagnosis_payload=ticket_payload_snapshot(payload) | {"isBatchTicket": is_batch},
            idempotent_key=idempotent_key,
            ticket_url=ticket_url,
        )
        db.add(ticket)
        db.flush()

        for item in payload["items"]:
            db.add(create_ticket_item(ticket_no, item))

        event = TicketEvent(
            ticket_no=ticket.ticket_no,
            event_type="CREATED",
            to_status="NEW",
            operator_account="SYSTEM",
            operator_name="SYSTEM",
            event_content=f"Dify diagnosis agent created ticket with {len(payload['items'])} item(s)",
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
                raise ValueError(f"ticket_no already exists: {requested_ticket_no}")
            continue

        db.refresh(ticket)
        return ticket, False

    raise RuntimeError("ticket_no generation conflict, please retry")


def list_ticket_items(db: Session, ticket_no: str) -> list[TicketItem]:
    return (
        db.query(TicketItem)
        .filter(TicketItem.ticket_no == ticket_no)
        .order_by(TicketItem.item_no.asc(), TicketItem.id.asc())
        .all()
    )


def count_ticket_items(db: Session, ticket_no: str) -> int:
    return db.query(TicketItem).filter(TicketItem.ticket_no == ticket_no).count()


def aggregate_ticket_status(db: Session, ticket_no: str) -> None:
    ticket = db.query(Ticket).filter(Ticket.ticket_no == ticket_no).first()
    if not ticket:
        return

    statuses = [item.status for item in list_ticket_items(db, ticket_no)]
    if not statuses:
        return

    old_status = ticket.status
    if all(status == "CLOSED" for status in statuses):
        ticket.status = "CLOSED"
        ticket.closed_at = ticket.closed_at or local_now()
    elif all(status in {"RESOLVED", "CLOSED"} for status in statuses):
        ticket.status = "RESOLVED"
        ticket.resolved_at = ticket.resolved_at or local_now()
    elif all(status == "NEW" for status in statuses):
        ticket.status = "NEW"
    else:
        ticket.status = "PROCESSING"

    if ticket.status != old_status:
        db.add(TicketEvent(
            ticket_no=ticket_no,
            event_type="STATUS_AGGREGATED",
            from_status=old_status,
            to_status=ticket.status,
            operator_account="SYSTEM",
            operator_name="SYSTEM",
            event_content="Ticket status aggregated from address item statuses",
        ))


def update_ticket_item_status(
    db: Session,
    ticket_no: str,
    item_id: int,
    status: str,
    reply_desc: str = "",
    operator_account: str = "",
    operator_name: str = "",
) -> TicketItem:
    if status not in ALLOWED_STATUSES:
        raise ValueError(f"invalid status: {status}")

    item = (
        db.query(TicketItem)
        .filter(TicketItem.ticket_no == ticket_no, TicketItem.id == item_id)
        .first()
    )
    if not item:
        raise ValueError("ticket item not found")

    old_status = item.status
    item.status = status
    item.reply_desc = reply_desc or item.reply_desc
    item.operator_account = operator_account or item.operator_account
    item.operator_name = operator_name or item.operator_name
    if status in {"RESOLVED", "CLOSED"}:
        item.processed_at = local_now()

    db.add(TicketEvent(
        ticket_no=ticket_no,
        event_type="ITEM_STATUS_CHANGED" if old_status != status else "ITEM_STATUS_REMARKED",
        from_status=old_status,
        to_status=status,
        operator_account=operator_account,
        operator_name=operator_name,
        event_content=f"{item.item_key}: {reply_desc or 'status updated'}",
    ))
    aggregate_ticket_status(db, ticket_no)
    db.commit()
    db.refresh(item)
    return item


def batch_update_ticket_item_status(
    db: Session,
    ticket_no: str,
    item_ids: list[int],
    status: str,
    reply_desc: str = "",
    operator_account: str = "",
    operator_name: str = "",
) -> list[TicketItem]:
    updated = []
    for item_id in item_ids:
        updated.append(
            update_ticket_item_status(
                db,
                ticket_no,
                item_id,
                status,
                reply_desc,
                operator_account,
                operator_name,
            )
        )
    return updated


def update_ticket_actual_reporter(
    db: Session,
    ticket_no: str,
    actual_reporter_account: str = "",
    operator_account: str = "",
    operator_name: str = "",
) -> Ticket:
    ticket = db.query(Ticket).filter(Ticket.ticket_no == ticket_no).first()
    if not ticket:
        raise ValueError("ticket not found")

    old_value = clean(ticket.actual_reporter_account)
    new_value = clean(actual_reporter_account)
    ticket.actual_reporter_account = new_value or None

    db.add(TicketEvent(
        ticket_no=ticket_no,
        event_type="ACTUAL_REPORTER_UPDATED",
        operator_account=operator_account,
        operator_name=operator_name,
        event_content=f"实际反馈用户从 {old_value or '-'} 改为 {new_value or '-'}",
    ))
    db.commit()
    db.refresh(ticket)
    return ticket

def update_ticket_status(
    db: Session,
    ticket_no: str,
    status: str,
    operator_account: str = "",
    operator_name: str = "",
    comment: str = "",
) -> Ticket:
    if status not in ALLOWED_STATUSES:
        raise ValueError(f"invalid status: {status}")

    ticket = db.query(Ticket).filter(Ticket.ticket_no == ticket_no).first()
    if not ticket:
        raise ValueError("ticket not found")

    old_status = ticket.status
    if old_status == "CLOSED":
        raise ValueError("closed ticket cannot be updated")
    if status == "CLOSED" and not clean(comment):
        raise ValueError("comment is required when closing ticket")

    ticket.status = status
    operator_display = clean(operator_name) or clean(operator_account)
    if operator_display:
        ticket.assigned_operator = operator_display

    if status == "RESOLVED":
        ticket.resolved_at = local_now()
    elif status == "CLOSED":
        ticket.closed_at = local_now()
        ticket.resolved_result = comment
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
            f"status changed from {old_status} to {status}"
            if status != old_status
            else f"remarked under {status}"
        ),
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
        raise ValueError("ticket not found")

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
        raise ValueError("ticket not found")

    old_status = ticket.status
    ticket.status = "CLOSED"
    ticket.resolved_result = resolved_result
    operator_display = clean(operator_name) or clean(operator_account)
    if operator_display:
        ticket.assigned_operator = operator_display
    ticket.closed_at = local_now()

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
