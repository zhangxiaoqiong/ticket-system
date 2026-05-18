import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Ticket, TicketEvent


def build_robot_message(ticket: Ticket) -> str:
    return f"""【地址诊断工单】{ticket.ticket_no}

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


async def notify_group(db: Session, ticket: Ticket) -> None:
    if not settings.robot_enabled or not settings.robot_webhook_url:
        return

    content = build_robot_message(ticket)

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
