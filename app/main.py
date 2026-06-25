from fastapi import FastAPI
from sqlalchemy import inspect, text

from app.config import settings
from app.database import engine
from app.models import Base
from app.routers import ticket_api, ticket_pages

Base.metadata.create_all(bind=engine)


def ensure_compatible_schema():
    inspector = inspect(engine)
    ticket_columns = {column["name"] for column in inspector.get_columns("ticket")}
    nullable_suffix = "" if engine.dialect.name == "sqlite" else " NULL"
    with engine.begin() as conn:
        if "reporter_group" not in ticket_columns:
            conn.execute(text(f"ALTER TABLE ticket ADD COLUMN reporter_group VARCHAR(256){nullable_suffix}"))
        if "actual_reporter_account" not in ticket_columns:
            conn.execute(text(f"ALTER TABLE ticket ADD COLUMN actual_reporter_account VARCHAR(128){nullable_suffix}"))
        if "reporter_group_name" not in ticket_columns:
            conn.execute(text(f"ALTER TABLE ticket ADD COLUMN reporter_group_name VARCHAR(256){nullable_suffix}"))


ensure_compatible_schema()

app = FastAPI(
    title="顺心分单诊断工单系统 MVP",
    root_path=settings.app_base_path,
)

app.include_router(ticket_api.router)
app.include_router(ticket_pages.router)


@app.get("/")
def index():
    return {"message": "顺心分单诊断工单系统 MVP 已启动"}
