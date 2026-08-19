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
    entityless_token_similarity_threshold: float = 0.55
    title_similarity_threshold: float = 0.85
    title_containment_threshold: float = 0.90
    title_jaccard_threshold: float = 0.55
    title_min_shared_tokens: int = 6
    # Shared-person-name title match (personnel stories whose subject isn't an
    # entity yet): lower bar than the syndication gates above because the name
    # bigram itself carries most of the evidence.
    title_name_jaccard_threshold: float = 0.40
    title_name_min_shared_tokens: int = 4
    # Topical-evidence gate (RM-4, brief 14). Entity overlap and event-type
    # compatibility may corroborate a merge but never cause one: a score-path
    # merge additionally requires shared non-entity headline vocabulary, or a
    # similar LLM summary. Deliberately permissive — the gate exists to block
    # the zero-evidence case, not to arbitrate close calls. See brief 15 for
    # the signal that decides the hard pairs.
    topic_evidence_threshold: float = 0.0
    summary_evidence_threshold: float = 0.45
    # Absolute ceiling on how far a cluster's first article may pre-date the
    # article being placed into it. Measured against the incoming variant's
    # publication time, never wall-clock, so a genuinely late syndicated copy
    # of an old story still finds its siblings. Stops a busy cluster from
    # being kept alive indefinitely by its own traffic.
    cluster_max_age_hours: int = 96
    # story_key (brief 15). Keys are compared by token overlap, not equality —
    # the model emits near-misses for the same event. Above the threshold two
    # articles are treated as the same story; below it, as different ones. A
    # missing key on either side is "no information", never a mismatch.
    story_key_agreement_threshold: float = 0.50

    # Ingestion age gate
    max_article_age_days: int = 7
    # Cross-check the article's own publication date (meta tags / JSON-LD) against
    # the feed-supplied date before ingesting. Aggregator feeds (Google Alerts,
    # SportSpyder, …) routinely re-surface old articles with a fresh <pubDate>,
    # which the feed-date age gate alone cannot catch. When enabled, RSS items
    # are fetched and re-checked against their true date, and items with no
    # resolvable date are rejected rather than defaulting to "now". Kill-switch:
    # set VERIFY_ARTICLE_PUBLISHED_DATE=false to fall back to feed-date-only.
    verify_article_published_date: bool = True

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

    # OpenRouter LLM settings (Gemini 2.5 Flash Lite via openrouter.ai). A small paid
    # model rather than a ":free" tier — the free tier is aggressively rate
    # limited and fails often; classify/relevance fall back to keywords on every
    # such failure, silently degrading the feed. Flash is cheap (~pennies/week at
    # our volume) and reliable for the JSON classification prompt.
    openrouter_api_key: str = ""
    openrouter_model: str = "google/gemini-2.5-flash-lite"
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

    # Monitoring / alerting (brief 09, O3). When set, the pipeline-health task
    # POSTs a short JSON alert to this webhook (ntfy/Discord/Slack-compatible)
    # on a degraded condition. Empty disables outbound alerts (logs only).
    alert_webhook_url: str = ""
    # Alerts for the same condition are not re-fired more often than this.
    alert_dedup_hours: int = 6

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
