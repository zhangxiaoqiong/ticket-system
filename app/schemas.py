from typing import Any, Dict, Literal, Optional
from pydantic import BaseModel


class CreateTicketRequest(BaseModel):
    ticketNo: Optional[str] = None
    ticketMode: Optional[str] = None
    sourceChannel: Optional[str] = None
    businessType: Optional[str] = None

    reporterAccount: Optional[str] = None
    reporterName: Optional[str] = None
    reporterGroup: Optional[str] = None
    reporterGroupName: Optional[str] = None
    notifyUserIds: Optional[list[str]] = None
    channelUserId: Optional[str] = None
    sessionId: Optional[str] = None

    userQuery: Optional[str] = None
    fullAddress: Optional[str] = None
    expectedResult: Optional[str] = None
    waybillNo: Optional[str] = None

    issueType: Optional[str] = None
    severityType: Optional[str] = None
    priority: Optional[Literal["P1", "P2", "P3", "P4"]] = None

    diagnosisSummary: Optional[str] = None
    internalSuggestion: Optional[str] = None
    customerReplyType: Optional[str] = None

    diagnosisPayload: Optional[Dict[str, Any]] = None
    summary: Optional[str] = None
    items: Optional[list[Dict[str, Any]]] = None
    idempotentKey: Optional[str] = None

    ticket_payload: Optional[Any] = None
    ticketPayload: Optional[Any] = None
    idempotent_key: Optional[str] = None
    owner_key: Optional[str] = None
    ticket_type: Optional[str] = None
    ticket_mode: Optional[str] = None
    is_batch_ticket: Optional[bool] = None
    batch_item_count: Optional[int] = None
    batch_reason: Optional[str] = None
    batch_severity_type: Optional[str] = None
    batch_priority: Optional[str] = None
    batch_diagnosis_summary: Optional[str] = None
    batch_full_address_text: Optional[str] = None
    batch_issue_summary_text: Optional[str] = None
    batch_full_diagnosis_text: Optional[str] = None
    batch_items: Optional[list[Dict[str, Any]]] = None
    user_query: Optional[str] = None
    reporter_account: Optional[str] = None
    reporter_group: Optional[str] = None
    reporter_group_name: Optional[str] = None
    channel_user_id: Optional[str] = None
    session_id: Optional[str] = None
    severity_type: Optional[str] = None
    diagnosis_summary: Optional[str] = None
    customer_reply_type: Optional[str] = None


class CreateTicketResponseData(BaseModel):
    ticketNo: str
    ticketUrl: str
    status: str
    duplicated: bool
    itemCount: int = 0


class ApiResponse(BaseModel):
    success: bool
    code: str
    message: str
    data: Optional[CreateTicketResponseData] = None


class UpdateStatusRequest(BaseModel):
    status: Literal["NEW", "PROCESSING", "RESOLVED", "CLOSED"]
    operatorAccount: Optional[str] = None
    operatorName: Optional[str] = None
    comment: Optional[str] = None


class AddCommentRequest(BaseModel):
    operatorAccount: Optional[str] = None
    operatorName: Optional[str] = None
    comment: str


class CloseTicketRequest(BaseModel):
    operatorAccount: Optional[str] = None
    operatorName: Optional[str] = None
    resolvedResult: str


class UpdateTicketItemRequest(BaseModel):
    status: Literal["NEW", "PROCESSING", "RESOLVED", "CLOSED"] = "RESOLVED"
    replyDesc: Optional[str] = None
    operatorAccount: Optional[str] = None
    operatorName: Optional[str] = None


class BatchUpdateTicketItemsRequest(BaseModel):
    itemIds: list[int]
    status: Literal["NEW", "PROCESSING", "RESOLVED", "CLOSED"] = "RESOLVED"
    replyDesc: Optional[str] = None
    operatorAccount: Optional[str] = None
    operatorName: Optional[str] = None
