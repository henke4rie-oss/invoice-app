from pydantic import Field
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    secret_key: str = Field(default="dev-secret-change-in-production")
    database_url: str = Field(default="sqlite:///./data/app.db")
    cors_origins: str = Field(default="http://localhost,http://127.0.0.1,http://localhost:8000,http://127.0.0.1:8000,http://localhost:5500,http://127.0.0.1:5500,null")
    scheduler_time: str = Field(default="09:00")
    scheduler_enabled: bool = Field(default=True)
    debug: bool = Field(default=True)
    smtp_host: str = Field(default="")
    smtp_port: int = Field(default=587)
    smtp_user: str = Field(default="")
    smtp_pass: str = Field(default="")
    smtp_from: str = Field(default="")
    smtp_use_tls: bool = Field(default=True)

settings = Settings()
