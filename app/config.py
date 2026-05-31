# app/config.py
"""Configuration management for AegisRAG"""
from typing import List
from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    """Application settings with environment variable support"""
    
    # Application
    app_version: str = "2.0.0"
    debug: bool = False
    
    # Security
    allowed_hosts: List[str] = ["localhost", "aegis_app", "0.0.0.0"]
    cors_origins: List[str] = ["http://localhost:3000", "http://localhost:8000"]
    cors_credentials: bool = False
    secret_key: str = "your-secret-key-change-in-production"
    
    # Database
    db_host: str = "aegis_db"
    db_port: int = 5432
    db_name: str = "aegis_rag"
    db_user: str = "aegis_admin"
    db_password: str = "SecUrE_Aegis_PaSsWoRd_2026"
    db_pool_size: int = 10
    db_pool_recycle: int = 3600
    db_connection_timeout: int = 30
    db_query_timeout: int = 60
    
    # Redis (optional caching)
    redis_enabled: bool = True
    redis_url: str = "redis://aegis_redis:6379/0"
    redis_ttl: int = 3600
    
    # Model configuration
    encoder_model: str = "all-MiniLM-L6-v2"
    vector_threshold: float = 0.3
    top_k_results: int = 5
    
    # Rate limiting
    rate_limit_enabled: bool = True
    rate_limit_per_minute: int = 100
    
    # Timeouts
    retrieval_timeout: int = 30
    generation_timeout: int = 30
    
    # Logging
    log_level: str = "INFO"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False

@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()
