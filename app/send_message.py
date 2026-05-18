import time
from typing import Any

import httpx


SEND_URL = "https://fs-next-api.sf-express.com/ump-biz/platform/send"
TOKEN_URL = "https://fs-next-api.sf-express.com/oauth2/token"


class Template1312:
    def __init__(
        self,
        title: str = "",
        range: str = "APPOINT",
        toGroupIds: list[str] | None = None,
        snapshot: str = "请查看消息",
        toNums: list[str] | None = None,
        text: str = "",
        buttons: list[dict[str, Any]] | None = None,
        pushContent: dict[str, str] | None = None,
    ):
        self.range = range
        self.title = title
        self.pushContent = pushContent or {"title": title, "body": title}
        self.toNums = toNums or []
        self.toGroupIds = toGroupIds or []
        self.snapshot = snapshot
        self.text = text
        self.buttons = buttons or []

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__


class SendTemplate:
    def __init__(self, batchId: str, sendTime: str, templateCode: str, body: dict[str, Any]):
        self.batchId = batchId
        self.sendTime = sendTime
        self.templateCode = templateCode
        self.body = body

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__


async def get_send_header(
    client_id: str,
    client_secret: str,
    token_url: str = TOKEN_URL,
    verify_ssl: bool = True,
) -> dict[str, str]:
    header_map = {"Content-Type": "application/x-www-form-urlencoded"}
    body_map = {
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "client_credentials",
    }

    async with httpx.AsyncClient(timeout=10, verify=verify_ssl) as client:
        response = await client.post(token_url, headers=header_map, data=body_map)
        response.raise_for_status()
        token_payload = response.json()

    access_token = token_payload.get("access_token")
    if not access_token:
        raise RuntimeError(f"丰声 Next 获取 token 失败：{token_payload}")

    return {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }


async def send_message(
    body: dict[str, Any],
    client_id: str,
    client_secret: str,
    send_url: str = SEND_URL,
    token_url: str = TOKEN_URL,
    verify_ssl: bool = True,
) -> dict[str, Any]:
    header = await get_send_header(
        client_id=client_id,
        client_secret=client_secret,
        token_url=token_url,
        verify_ssl=verify_ssl,
    )

    async with httpx.AsyncClient(timeout=10, verify=verify_ssl) as client:
        response = await client.post(send_url, headers=header, json=body)
        response.raise_for_status()
        return response.json()


async def send_template_1312(
    *,
    client_id: str,
    client_secret: str,
    group_ids: list[str],
    title: str,
    text: str,
    ticket_url: str,
    snapshot: str = "请查看工单消息",
    template_code: str = "1312",
    send_url: str = SEND_URL,
    token_url: str = TOKEN_URL,
    verify_ssl: bool = True,
) -> dict[str, Any]:
    buttons = [
        {
            "text": "去处理",
            "textSelected": "已处理",
            "actionType": "JUMP_NORMAL_URL",
            "url": ticket_url,
        }
    ]
    template = Template1312(
        title=title,
        snapshot=snapshot,
        toGroupIds=group_ids,
        text=text,
        buttons=buttons,
    )
    send_time = str(int(time.time() * 1000))
    body = SendTemplate(
        batchId=send_time,
        sendTime=send_time,
        templateCode=template_code,
        body=template.to_dict(),
    )
    return await send_message(
        body.to_dict(),
        client_id=client_id,
        client_secret=client_secret,
        send_url=send_url,
        token_url=token_url,
        verify_ssl=verify_ssl,
    )
