import json
import re
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Ticket, TicketEvent, TicketItem
from app.send_message import send_template_1312

MOBILE_PATTERN = re.compile(r"^1\d{10}$")


def split_values(value: str) -> list[str]:
    return [item.strip() for item in (value or "").split(",") if item.strip()]


def normalize_values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return split_values(str(value))


def parse_json_map(value: str, setting_name: str) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{setting_name} must be valid JSON") from exc
    if not isinstance(parsed, dict):
        raise ValueError(f"{setting_name} must be a JSON object")
    return parsed


def ticket_ops_match_keys(ticket: Ticket) -> list[str]:
    return [
        ticket.business_type or "",
        ticket.source_channel or "",
        ticket.priority or "",
        "default",
    ]


def ticket_user_match_keys(ticket: Ticket) -> list[str]:
    return [
        ticket.reporter_group or "",
        ticket.reporter_account or "",
        ticket.channel_user_id or "",
        ticket.owner_key or "",
        "default",
    ]


def resolve_map_value(mapping: dict[str, Any], ticket: Ticket, match_keys: list[str] | None = None) -> Any:
    for key in match_keys or ticket_ops_match_keys(ticket):
        if key and key in mapping:
            return mapping[key]
    return None


def normalize_at_value(value: Any) -> dict[str, list[str]]:
    if not value:
        return {"atMobiles": [], "atUserIds": []}
    if isinstance(value, dict):
        return {
            "atMobiles": normalize_values(value.get("atMobiles") or value.get("mobiles")),
            "atUserIds": normalize_values(value.get("atUserIds") or value.get("userIds")),
        }

    values = normalize_values(value)
    return {
        "atMobiles": [item for item in values if MOBILE_PATTERN.match(item)],
        "atUserIds": [item for item in values if not MOBILE_PATTERN.match(item)],
    }


def merge_at_targets(*targets: dict[str, list[str]]) -> dict[str, list[str]]:
    merged = {"atMobiles": [], "atUserIds": []}
    for target in targets:
        for key in merged:
            for item in target.get(key, []):
                if item and item not in merged[key]:
                    merged[key].append(item)
    return merged


def infer_ticket_at_targets(ticket: Ticket) -> dict[str, list[str]]:
    mobiles: list[str] = []
    user_ids: list[str] = []
    if ticket.reporter_account and MOBILE_PATTERN.match(ticket.reporter_account):
        mobiles.append(ticket.reporter_account)
    elif ticket.reporter_account:
        user_ids.append(ticket.reporter_account)
    if ticket.channel_user_id and ticket.channel_user_id not in user_ids:
        user_ids.append(ticket.channel_user_id)
    return {"atMobiles": mobiles, "atUserIds": user_ids}


def resolve_ticket_notify_user_ids(ticket: Ticket) -> list[str]:
    payload = ticket.diagnosis_payload or {}
    return normalize_values(payload.get("notifyUserIds"))


def resolve_robot_at_targets(ticket: Ticket, items: list[TicketItem] | None = None) -> dict[str, list[str]]:
    at_map = parse_json_map(settings.robot_at_map, "robot_at_map")
    mapped = normalize_at_value(resolve_map_value(at_map, ticket, ticket_user_match_keys(ticket)))
    configured = {
        "atMobiles": split_values(settings.robot_at_mobiles),
        "atUserIds": split_values(settings.robot_at_user_ids),
    }
    payload_targets = {"atMobiles": [], "atUserIds": resolve_ticket_notify_user_ids(ticket)}

    item_user_ids: list[str] = []
    for item in items or []:
        item_user_ids.extend(normalize_values(item.notify_user_ids))
    item_targets = {"atMobiles": [], "atUserIds": item_user_ids}

    return merge_at_targets(configured, mapped, payload_targets, item_targets, infer_ticket_at_targets(ticket))


def resolve_robot_webhook_url(ticket: Ticket) -> str:
    webhook_map = parse_json_map(settings.robot_webhook_map, "robot_webhook_map")
    mapped = resolve_map_value(webhook_map, ticket, ticket_ops_match_keys(ticket))
    if isinstance(mapped, list):
        return str(mapped[0]).strip() if mapped else ""
    if mapped:
        return str(mapped).strip()
    return settings.robot_webhook_url


def resolve_processed_robot_webhook_url(ticket: Ticket) -> str:
    webhook_map = parse_json_map(settings.robot_processed_webhook_map, "robot_processed_webhook_map")
    mapped = resolve_map_value(webhook_map, ticket, ticket_user_match_keys(ticket))
    if isinstance(mapped, list):
        return str(mapped[0]).strip() if mapped else ""
    if mapped:
        return str(mapped).strip()
    return settings.robot_processed_webhook_url


def resolve_fs_next_group_ids(ticket: Ticket) -> list[str]:
    group_map = parse_json_map(settings.fs_next_group_map, "fs_next_group_map")
    mapped = resolve_map_value(group_map, ticket, ticket_ops_match_keys(ticket))
    if mapped is not None:
        return normalize_values(mapped)
    return split_values(settings.fs_next_group_ids)


def append_mobile_at_text(content: str, at_targets: dict[str, list[str]]) -> str:
    mobiles = [f"@{mobile}" for mobile in at_targets.get("atMobiles", [])]
    if not mobiles:
        return content
    return f"{content}\n\n{' '.join(mobiles)}"


def build_robot_payload(content: str, at_targets: dict[str, list[str]] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "msgtype": "text",
        "text": {
            "content": append_mobile_at_text(content, at_targets or {}),
        },
    }
    if at_targets and (at_targets.get("atMobiles") or at_targets.get("atUserIds")):
        payload["at"] = {
            "atMobiles": at_targets.get("atMobiles", []),
            "atUserIds": at_targets.get("atUserIds", []),
            "isAtAll": False,
        }
    return payload


async def post_robot_payload(webhook_url: str, payload: dict[str, Any]) -> httpx.Response:
    headers = {"Content-Type": "application/json"}
    proxy_url = settings.robot_proxy_url or None
    if not proxy_url:
        async with httpx.AsyncClient(timeout=5) as client:
            return await client.post(webhook_url, headers=headers, json=payload)

    try:
        async with httpx.AsyncClient(timeout=5, proxy=proxy_url) as client:
            return await client.post(webhook_url, headers=headers, json=payload)
    except TypeError:
        async with httpx.AsyncClient(timeout=5, proxies=proxy_url) as client:
            return await client.post(webhook_url, headers=headers, json=payload)


async def send_robot_message(
    db: Session,
    ticket: Ticket,
    *,
    content: str,
    event_type: str,
    failure_event_type: str,
    at_targets: dict[str, list[str]] | None = None,
    webhook_url: str | None = None,
    skip_global_switch: bool = False,
) -> bool:
    # skip_global_switch=True 时，只检查对应的功能开关，不检查 robot_enabled 总开关
    if not skip_global_switch and not settings.robot_enabled:
        return False

    webhook_url = webhook_url if webhook_url is not None else resolve_robot_webhook_url(ticket)
    if not webhook_url:
        return False

    try:
        payload = build_robot_payload(content, at_targets)
        resp = await post_robot_payload(webhook_url, payload)
        event = TicketEvent(
            ticket_no=ticket.ticket_no,
            event_type=event_type,
            event_content=f"robot message sent, status={resp.status_code}, response={resp.text[:500]}",
        )
        db.add(event)
        db.commit()
        return True
    except Exception as exc:
        event = TicketEvent(
            ticket_no=ticket.ticket_no,
            event_type=failure_event_type,
            event_content=f"robot message failed: {repr(exc)}",
        )
        db.add(event)
        db.commit()
        return False


def clean_text(value: Any, default: str = "-") -> str:
    text = str(value or "").strip()
    return text if text else default


def compact_text(value: Any, max_length: int = 180) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    if not text:
        return "-"
    if len(text) <= max_length:
        return text
    return f"{text[:max_length]}..."


def item_suggestion_text(item: TicketItem) -> str:
    suggestion = item.operation_suggestion or {}
    if isinstance(suggestion, dict):
        return compact_text(suggestion.get("suggestion") or suggestion.get("problemDiagnosis"))
    return compact_text(suggestion)


def item_problem_text(item: TicketItem) -> str:
    return compact_text(item.issue_description or item.user_query)


def item_issue_types(ticket: Ticket, items: list[TicketItem]) -> str:
    values: list[str] = []
    for value in [ticket.issue_type, *(item.issue_type for item in items)]:
        text = clean_text(value, "")
        if text and text not in values:
            values.append(text)
    return "、".join(values) if values else "-"


def address_summary(items: list[TicketItem], max_items: int = 5) -> str:
    addresses = [clean_text(item.full_address, "") for item in items]
    addresses = [address for address in addresses if address]
    if not addresses:
        return "-"
    lines = [f"{index}. {address}" for index, address in enumerate(addresses[:max_items], start=1)]
    if len(addresses) > max_items:
        lines.append(f"...等 {len(addresses)} 条")
    return "\n".join(lines)


def build_robot_message(ticket: Ticket, items: list[TicketItem] | None = None) -> str:
    items = sorted(items or [], key=lambda item: item.item_no or 0)
    reporter = clean_text(ticket.reporter_account or ticket.channel_user_id)
    reporter_group = clean_text(ticket.reporter_group)

    lines = [
        f"【顺心分单诊断工单】{ticket.ticket_no}",
        "",
        f"优先级：{clean_text(ticket.priority)}",
        f"问题类型：{item_issue_types(ticket, items)}",
        f"反馈群：{reporter_group}",
        f"用户账号：{reporter}",
    ]

    if len(items) > 1:
        lines.extend([
            "",
            f"地址数量：{len(items)}",
            f"地址摘要：\n{address_summary(items)}",
            "",
            "诊断结论：批量地址诊断已完成，请进入工单详情逐条查看。",
            "处理建议：请在工单详情中按地址明细处理，可单条处理或批量处理。",
        ])
    elif len(items) == 1:
        item = items[0]
        lines.extend(["", f"地址数量：{len(items)}"])
        lines.extend([
            "",
            f"地址：{clean_text(item.full_address)}",
            f"反馈问题：{item_problem_text(item)}",
            f"诊断结论：{compact_text(item.diagnosis_summary)}",
            f"处理建议：{item_suggestion_text(item)}",
        ])
    else:
        lines.extend([
            "",
            f"地址：{clean_text(ticket.full_address)}",
            "",
            f"诊断结论：{compact_text(ticket.diagnosis_summary)}",
            f"处理建议：{compact_text(ticket.internal_suggestion)}",
        ])

    lines.extend(["", f"工单链接：{clean_text(ticket.ticket_url)}"])
    return "\n".join(lines)


def build_items_processed_message(items: list[TicketItem], reply_desc: str = "") -> str:
    lines = ["你反馈的地址问题已处理："]
    for index, item in enumerate(items, start=1):
        result = reply_desc or item.reply_desc or ""
        lines.extend([
            "",
            f"{index}. 地址：{item.full_address or '-'}",
            f"反馈问题：{item.issue_description or item.user_query or '-'}",
            f"处理结果：{result or '-'}",
        ])
    return "\n".join(lines)


async def notify_fs_next(db: Session, ticket: Ticket, content: str) -> bool:
    if not settings.fs_next_enabled:
        return False

    group_ids = resolve_fs_next_group_ids(ticket)
    if not group_ids:
        return False

    if not settings.fs_next_client_id or not settings.fs_next_client_secret:
        event = TicketEvent(
            ticket_no=ticket.ticket_no,
            event_type="FS_NEXT_NOTIFY_SKIPPED",
            event_content="fs_next notification skipped: missing client_id or client_secret",
        )
        db.add(event)
        db.commit()
        return False

    result = await send_template_1312(
        client_id=settings.fs_next_client_id,
        client_secret=settings.fs_next_client_secret,
        group_ids=group_ids,
        title=f"顺心分单诊断工单 {ticket.ticket_no}",
        text=content,
        ticket_url=ticket.ticket_url,
        snapshot=f"新工单：{ticket.ticket_no}",
        template_code=settings.fs_next_template_code,
        send_url=settings.fs_next_send_url,
        token_url=settings.fs_next_token_url,
        verify_ssl=settings.fs_next_verify_ssl,
    )

    event = TicketEvent(
        ticket_no=ticket.ticket_no,
        event_type="FS_NEXT_NOTIFIED",
        event_content=f"fs_next message sent, groups={','.join(group_ids)}, response={json.dumps(result, ensure_ascii=False)[:1000]}",
    )
    db.add(event)
    db.commit()
    return True


async def notify_group(db: Session, ticket: Ticket) -> None:
    """创建工单时通知运营群：优先使用丰声Next，不使用钉钉webhook。"""
    try:
        items = (
            db.query(TicketItem)
            .filter(TicketItem.ticket_no == ticket.ticket_no)
            .order_by(TicketItem.item_no.asc(), TicketItem.id.asc())
            .all()
        )
        content = build_robot_message(ticket, items)
        await notify_fs_next(db, ticket, content)
    except Exception as exc:
        event = TicketEvent(
            ticket_no=ticket.ticket_no,
            event_type="FS_NEXT_NOTIFY_FAILED",
            event_content=f"fs_next message failed: {str(exc)}",
        )
        db.add(event)
        db.commit()


def processed_statuses() -> set[str]:
    return set(split_values(settings.robot_processed_statuses))


async def notify_ticket_items_processed(
    db: Session,
    *,
    ticket_no: str,
    items: list[TicketItem],
    operator_account: str = "",
    operator_name: str = "",
    reply_desc: str = "",
) -> None:
    if not settings.robot_processed_notify_enabled:
        return

    processed_items = [item for item in items if item.status in processed_statuses()]
    if not processed_items:
        return

    ticket = db.query(Ticket).filter(Ticket.ticket_no == ticket_no).first()
    if not ticket:
        return

    content = build_items_processed_message(processed_items, reply_desc=reply_desc)
    at_targets = resolve_robot_at_targets(ticket, processed_items)
    await send_robot_message(
        db,
        ticket,
        content=content,
        at_targets=at_targets,
        webhook_url=resolve_processed_robot_webhook_url(ticket),
        event_type="BOT_ITEMS_PROCESSED_NOTIFIED",
        failure_event_type="BOT_ITEMS_PROCESSED_NOTIFY_FAILED",
        skip_global_switch=True,  # 处理完成通知独立控制，不受 robot_enabled 总开关影响
    )
