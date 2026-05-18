from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "地址诊断工单系统"
    base_url: str = "http://127.0.0.1:8000"

    database_url: str = "mysql+pymysql://root:password@127.0.0.1:3306/ticket_mvp?charset=utf8mb4"

    robot_webhook_url: str = ""
    robot_enabled: bool = True

    class Config:
        env_file = ".env"


settings = Settings()
