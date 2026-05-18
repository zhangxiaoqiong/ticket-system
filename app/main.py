from fastapi import FastAPI
from app.config import settings
from app.database import engine
from app.models import Base
from app.routers import ticket_api, ticket_pages

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="顺心分单诊断工单系统 MVP",
    root_path=settings.app_base_path,
)

app.include_router(ticket_api.router)
app.include_router(ticket_pages.router)


@app.get("/")
def index():
    return {"message": "顺心分单诊断工单系统 MVP 已启动"}
