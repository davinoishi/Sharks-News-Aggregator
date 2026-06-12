from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    celery_broker_url: str
    celery_result_backend: str
    allowed_origins: str = "http://localhost:3000"

    # API settings
    api_title: str = "Sharks Aggregator API"
    api_version: str = "0.1.0"

    # Public-facing site URL, used for channel metadata in the published RSS
    # feed (/rss). Item links always point at the real source URLs. Override in
    # production via PUBLIC_SITE_URL.
    public_site_url: str = "http://localhost:3000"

    # Ingestion settings
    ingest_interval_minutes: int = 10
    max_fetch_retries: int = 3
    request_timeout_seconds: int = 30

    # Clustering settings
    cluster_time_window_hours: int = 72
    cluster_similarity_threshold: float = 0.62
    entity_overlap_threshold: float = 0.50
    token_similarity_threshold: float = 0.40

    # Ingestion age gate
    max_article_age_days: int = 7

    # Rate limiting
    submission_rate_limit_per_ip: int = 10  # per hour
    # Cheap per-client limit for public write/counter endpoints
    # (/metrics/pageview, /cluster/{id}/click). Generous on purpose — the goal
    # is stopping trivial counter spam, not precision.
    metrics_rate_limit_per_min: int = 60

    # SSRF guard for user-submitted links (see app/core/url_guard.py)
    submission_allowed_ports: str = "80,443"
    submission_max_redirects: int = 5
    submission_fetch_max_bytes: int = 5_242_880  # 5 MB

    # Privacy: salt used when hashing submitter IPs before storage. Set a
    # stable, secret value in the environment (empty = unsalted, less secure).
    ip_hash_salt: str = ""

    # OpenRouter LLM settings (Gemma 4 via openrouter.ai)
    openrouter_api_key: str = ""
    openrouter_model: str = "google/gemma-4-26b-a4b-it:free"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_timeout_seconds: int = 45
    llm_relevance_enabled: bool = True
    llm_evaluation_mode: bool = False
    llm_tagging_enabled: bool = True
    llm_clustering_enabled: bool = True

    # Admin settings
    # API-key auth injected by the Next.js proxy. If empty/unset, all admin
    # requests are denied (fail closed). There is no IP-based fallback: behind
    # the Next.js proxy the backend only ever sees the proxy/tunnel IP.
    admin_api_key: str = ""

    # Trusted proxies. X-Forwarded-For is honored ONLY when the direct peer is
    # one of these networks (the Next.js container on the Docker bridge);
    # otherwise the direct peer IP is used. Comma-separated IPs/CIDRs.
    trusted_proxy_ips: str = "127.0.0.1,::1,172.16.0.0/12"

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
