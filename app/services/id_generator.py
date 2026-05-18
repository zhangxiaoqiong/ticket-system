from datetime import datetime
from sqlalchemy.orm import Session

from app.models import Ticket


def generate_ticket_no(db: Session) -> str:
    today = datetime.now().strftime("%Y%m%d")
    prefix = f"ADDR{today}"

    count = (
        db.query(Ticket)
        .filter(Ticket.ticket_no.like(f"{prefix}%"))
        .count()
    )

    seq = count + 1
    return f"{prefix}{seq:04d}"
