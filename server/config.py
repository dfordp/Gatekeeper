from typing import Optional
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    """Application configuration from environment variables."""
    
    # Database
    database_url: str = "postgresql://gatekeeper_user:gatekeeper_secure_password_123@localhost:5432/gatekeeper_db"
    
    # Qdrant
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: Optional[str] = None
    
    # JWT
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expiration_hours: int = 24
    jwt_refresh_expiration_days: int = 7
    
    # API
    api_title: str = "Gatekeeper Support Platform"
    api_version: str = "1.0.0"
    debug: bool = False
    
    # CORS
    cors_origins: list[str] = ["http://localhost:3000"]
    
    # Email
    smtp_host: Optional[str] = None
    smtp_port: int = 587
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None
    
    # Logging
    log_level: str = "INFO"
    
    class Config:
        env_file = ".env"
        case_sensitive = False

settings = Settings()