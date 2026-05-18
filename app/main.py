from fastapi import FastAPI
from app.database import engine
from app.models import Base
from app.routers import ticket_api, ticket_pages

Base.metadata.create_all(bind=engine)

app = FastAPI(title="地址诊断工单系统 MVP")

app.include_router(ticket_api.router)
app.include_router(ticket_pages.router)


@app.get("/")
def index():
    return {"message": "地址诊断工单系统 MVP 已启动"}
