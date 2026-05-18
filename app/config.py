from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "顺心分单诊断工单系统"
    base_url: str = "http://127.0.0.1:8000"

    database_url: str = "mysql+pymysql://root:password@127.0.0.1:3306/ticket_mvp?charset=utf8mb4"

    robot_webhook_url: str = ""
    robot_enabled: bool = True

    fs_next_enabled: bool = True
    fs_next_client_id: str = ""
    fs_next_client_secret: str = ""
    fs_next_group_ids: str = ""
    fs_next_group_map: str = ""
    fs_next_template_code: str = "1312"
    fs_next_send_url: str = "https://fs-next-api.sf-express.com/ump-biz/platform/send"
    fs_next_token_url: str = "https://fs-next-api.sf-express.com/oauth2/token"
    fs_next_verify_ssl: bool = True

    class Config:
        env_file = ".env"


settings = Settings()
