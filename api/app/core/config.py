from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    celery_broker_url: str
    celery_result_backend: str
    allowed_origins: str = "http://localhost:3000"

    # API settings
    api_title: str = "Sharks Aggregator API"
    api_version: str = "0.1.0"

    # Ingestion settings
    ingest_interval_minutes: int = 10
    max_fetch_retries: int = 3
    request_timeout_seconds: int = 30

    # Clustering settings
    cluster_time_window_hours: int = 72
    cluster_similarity_threshold: float = 0.62
    entity_overlap_threshold: float = 0.50
    token_similarity_threshold: float = 0.40

    # Rate limiting
    submission_rate_limit_per_ip: int = 10  # per hour

    # Ollama LLM settings (Hailo-Ollama on Pi5-AI2)
    ollama_base_url: str = "http://localhost:8000"
    ollama_model: str = "qwen2.5-instruct:1.5b"
    ollama_timeout_seconds: int = 30
    llm_relevance_enabled: bool = True
    # Shadow mode: keyword decides, LLM evaluates for comparison report
    llm_evaluation_mode: bool = False

    # Admin settings
    admin_allowed_ips: str = "127.0.0.1,192.168.0.0/24,10.0.0.0/8"
    admin_api_key: str = ""  # Optional for external access

    # BlueSky posting settings
    bluesky_enabled: bool = False
    bluesky_handle: str = ""
    bluesky_app_password: str = ""
    bluesky_min_sources: int = 1
    bluesky_post_interval_minutes: int = 15

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
