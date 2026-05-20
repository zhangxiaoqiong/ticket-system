from datetime import datetime
from sqlalchemy import (
    Column, BigInteger, String, Text, DateTime, JSON, Index
)
from sqlalchemy.orm import declarative_base

Base = declarative_base()


def local_now():
    return datetime.now()


class Ticket(Base):
    __tablename__ = "ticket"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    ticket_no = Column(String(64), unique=True, nullable=False)

    source_channel = Column(String(64), nullable=False)
    business_type = Column(String(64), nullable=False)

    status = Column(String(32), nullable=False, default="NEW")
    priority = Column(String(16), nullable=False, default="P3")
    severity_type = Column(String(32))
    issue_type = Column(String(128))

    reporter_account = Column(String(128))
    reporter_name = Column(String(128))
    channel_user_id = Column(String(128))
    session_id = Column(String(128))
    owner_key = Column(String(256), nullable=False)

    user_query = Column(Text)
    full_address = Column(Text)
    expected_result = Column(String(512))
    waybill_no = Column(String(128))

    diagnosis_summary = Column(Text)
    internal_suggestion = Column(Text)
    customer_reply_type = Column(String(64))

    diagnosis_payload = Column(JSON)

    idempotent_key = Column(String(128), unique=True, nullable=False)
    ticket_url = Column(String(512))

    assigned_operator = Column(String(128))
    resolved_result = Column(Text)

    created_at = Column(DateTime, default=local_now, nullable=False)
    updated_at = Column(DateTime, default=local_now, onupdate=local_now, nullable=False)
    resolved_at = Column(DateTime)
    closed_at = Column(DateTime)


Index("idx_ticket_no", Ticket.ticket_no)
Index("idx_owner_key", Ticket.owner_key)
Index("idx_status", Ticket.status)
Index("idx_priority", Ticket.priority)
Index("idx_created_at", Ticket.created_at)
Index("idx_reporter_account", Ticket.reporter_account)


class TicketEvent(Base):
    __tablename__ = "ticket_event"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    ticket_no = Column(String(64), nullable=False)
    event_type = Column(String(64), nullable=False)

    from_status = Column(String(32))
    to_status = Column(String(32))

    operator_account = Column(String(128))
    operator_name = Column(String(128))
    event_content = Column(Text)

    created_at = Column(DateTime, default=local_now, nullable=False)


Index("idx_event_ticket_no", TicketEvent.ticket_no)
Index("idx_event_created_at", TicketEvent.created_at)
