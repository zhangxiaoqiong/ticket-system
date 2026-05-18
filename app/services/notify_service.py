import json

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Ticket, TicketEvent
from app.send_message import send_template_1312


def build_robot_message(ticket: Ticket) -> str:
    return f"""【顺心分单诊断工单】{ticket.ticket_no}

优先级：{ticket.priority}
问题类型：{ticket.issue_type or ""}
用户账号：{ticket.reporter_account or ticket.channel_user_id or ""}

地址：
{ticket.full_address or ""}

用户期望：
{ticket.expected_result or ""}

诊断结论：
{ticket.diagnosis_summary or ""}

处理建议：
{ticket.internal_suggestion or ""}

工单链接：
{ticket.ticket_url}
"""


def split_group_ids(value: str) -> list[str]:
    return [item.strip() for item in (value or "").split(",") if item.strip()]


def resolve_fs_next_group_ids(ticket: Ticket) -> list[str]:
    if settings.fs_next_group_map:
        group_map = json.loads(settings.fs_next_group_map)
        for key in (
            ticket.business_type,
            ticket.source_channel,
            ticket.priority,
            "default",
        ):
            if key and key in group_map:
                mapped = group_map[key]
                if isinstance(mapped, list):
                    return [str(item).strip() for item in mapped if str(item).strip()]
                return split_group_ids(str(mapped))

    return split_group_ids(settings.fs_next_group_ids)


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
            event_content="丰声 Next 消息未发送：缺少 fs_next_client_id 或 fs_next_client_secret",
        )
        db.add(event)
        db.commit()
        return True

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
        event_content=f"丰声 Next 消息推送完成，群：{','.join(group_ids)}，响应：{json.dumps(result, ensure_ascii=False)[:1000]}",
    )
    db.add(event)
    db.commit()
    return True


async def notify_group(db: Session, ticket: Ticket) -> None:
    if not settings.robot_enabled or not settings.robot_webhook_url:
        if not settings.robot_enabled:
            return

    content = build_robot_message(ticket)

    try:
        if await notify_fs_next(db, ticket, content):
            return
    except Exception as e:
        event = TicketEvent(
            ticket_no=ticket.ticket_no,
            event_type="FS_NEXT_NOTIFY_FAILED",
            event_content=f"丰声 Next 消息推送失败：{str(e)}",
        )
        db.add(event)
        db.commit()
        return

    if not settings.robot_webhook_url:
        return

    try:
        payload = {
            "msgtype": "text",
            "text": {
                "content": content
            }
        }

        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.post(settings.robot_webhook_url, json=payload)

        event = TicketEvent(
            ticket_no=ticket.ticket_no,
            event_type="BOT_NOTIFIED",
            event_content=f"机器人推送完成，状态码：{resp.status_code}，响应：{resp.text[:500]}"
        )
        db.add(event)
        db.commit()

    except Exception as e:
        event = TicketEvent(
            ticket_no=ticket.ticket_no,
            event_type="NOTIFY_FAILED",
            event_content=f"机器人推送失败：{str(e)}"
        )
        db.add(event)
        db.commit()
