from typing import Any, Dict, Literal, Optional
from pydantic import BaseModel


class CreateTicketRequest(BaseModel):
    ticketNo: Optional[str] = None
    sourceChannel: str
    businessType: str

    reporterAccount: Optional[str] = None
    reporterName: Optional[str] = None
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
    idempotentKey: Optional[str] = None


class CreateTicketResponseData(BaseModel):
    ticketNo: str
    ticketUrl: str
    status: str
    duplicated: bool


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
