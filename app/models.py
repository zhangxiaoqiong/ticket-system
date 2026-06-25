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
    actual_reporter_account = Column(String(128))
    reporter_name = Column(String(128))
    reporter_group = Column(String(256))
    reporter_group_name = Column(String(256))
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
Index("idx_actual_reporter_account", Ticket.actual_reporter_account)


class TicketItem(Base):
    __tablename__ = "ticket_item"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    ticket_no = Column(String(64), nullable=False)
    item_key = Column(String(128), nullable=False)
    item_no = Column(BigInteger, nullable=False, default=1)

    status = Column(String(32), nullable=False, default="NEW")
    priority = Column(String(16), nullable=False, default="P3")
    severity_type = Column(String(32))
    issue_type = Column(String(128))

    full_address = Column(Text)
    user_query = Column(Text)
    issue_description = Column(Text)
    expected_result = Column(String(512))
    waybill_no = Column(String(128))

    diagnosis_summary = Column(Text)
    diagnosis_text = Column(Text)
    customer_reply_reference = Column(Text)
    operation_suggestion = Column(JSON)
    v5_result = Column(JSON)
    village_result = Column(JSON)
    diagnosis_payload = Column(JSON)
    notify_user_ids = Column(JSON)

    reply_desc = Column(Text)
    operator_account = Column(String(128))
    operator_name = Column(String(128))
    processed_at = Column(DateTime)

    created_at = Column(DateTime, default=local_now, nullable=False)
    updated_at = Column(DateTime, default=local_now, onupdate=local_now, nullable=False)


Index("idx_ticket_item_ticket_no", TicketItem.ticket_no)
Index("idx_ticket_item_key", TicketItem.item_key)
Index("idx_ticket_item_status", TicketItem.status)


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
