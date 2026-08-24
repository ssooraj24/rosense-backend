import os
from typing import List, Union, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    PROJECT_NAME: str = "RoSense AI Backend API"
    API_V1_STR: str = "/api/v1"
    
    # Environment mode: 'cloud' or 'docker_onprem'
    SUPABASE_ENV: str = "cloud"
    
    # Supabase Parameters
    SUPABASE_URL: str = "https://your-project-ref.supabase.co"
    SUPABASE_ANON_KEY: str = "your-supabase-anon-key"
    SUPABASE_SERVICE_ROLE_KEY: str = "your-supabase-service-role-key"
    
    # Asymmetric Key verification (ECC P-256 / ES256) - Recommended for modern Supabase
    SUPABASE_JWKS_URL: Optional[str] = None
    
    # Legacy Symmetric HS256 Secret (Optional for legacy Supabase projects)
    JWT_SECRET: Optional[str] = None
    
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/postgres"
    
    # CORS Origins (Allow localhost, 127.0.0.1, local IP adapters, and production frontend)
    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:3030",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3030",
        "http://192.168.56.1:3030",
        "https://rosenseai.vercel.app",
        "*"
    ]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
