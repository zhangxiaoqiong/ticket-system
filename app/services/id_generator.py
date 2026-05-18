from datetime import datetime

from sqlalchemy.orm import Session


def generate_ticket_no(db: Session) -> str:
    return f"SX{datetime.now():%y%m%d%H%M%S}"
