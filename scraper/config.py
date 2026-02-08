"""Configuration management using Pydantic Settings."""

from typing import List
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class RabbitMQSettings(BaseSettings):
    """RabbitMQ connection configuration."""
    
    host: str = Field(default="localhost", alias="RABBITMQ_HOST")
    port: int = Field(default=5672, alias="RABBITMQ_PORT")
    user: str = Field(default="guest", alias="RABBITMQ_USER")
    password: str = Field(default="guest", alias="RABBITMQ_PASSWORD")
    vhost: str = Field(default="/", alias="RABBITMQ_VHOST")
    
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    
    @property
    def url(self) -> str:
        """Construct AMQP URL."""
        return f"amqp://{self.user}:{self.password}@{self.host}:{self.port}/{self.vhost}"


class VLLMSettings(BaseSettings):
    """vLLM inference server configuration."""
    
    base_url: str = Field(default="http://localhost:8000/v1", alias="VLLM_BASE_URL")
    api_key: str = Field(default="token", alias="VLLM_API_KEY")
    model_name: str = Field(default="meta-llama/Meta-Llama-3.1-8B-Instruct", alias="VLLM_MODEL_NAME")
    max_tokens: int = Field(default=512, alias="VLLM_MAX_TOKENS")
    temperature: float = Field(default=0.1, alias="VLLM_TEMPERATURE")
    
    # Rate limiting and backoff settings
    max_concurrent_requests: int = Field(default=2, alias="VLLM_MAX_CONCURRENT")
    requests_per_minute: int = Field(default=20, alias="VLLM_REQUESTS_PER_MINUTE")
    max_retries: int = Field(default=5, alias="VLLM_MAX_RETRIES")
    base_backoff_seconds: float = Field(default=1.0, alias="VLLM_BASE_BACKOFF")
    max_backoff_seconds: float = Field(default=60.0, alias="VLLM_MAX_BACKOFF")
    
    # Circuit breaker settings
    circuit_breaker_threshold: int = Field(default=5, alias="VLLM_CIRCUIT_BREAKER_THRESHOLD")
    circuit_breaker_timeout: int = Field(default=60, alias="VLLM_CIRCUIT_BREAKER_TIMEOUT")
    
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


class QueueSettings(BaseSettings):
    """RabbitMQ queue configuration."""
    
    discovery_queue: str = Field(default="discovery_queue", alias="DISCOVERY_QUEUE_NAME")
    extraction_queue: str = Field(default="extraction_queue", alias="EXTRACTION_QUEUE_NAME")
    repair_queue: str = Field(default="repair_queue", alias="REPAIR_QUEUE_NAME")
    max_priority: int = Field(default=10, alias="QUEUE_MAX_PRIORITY")
    
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


class WorkerSettings(BaseSettings):
    """Worker process configuration."""
    
    discovery_workers: int = Field(default=2, alias="DISCOVERY_WORKERS")
    extraction_workers: int = Field(default=4, alias="EXTRACTION_WORKERS")
    repair_workers: int = Field(default=1, alias="REPAIR_WORKERS")
    # Reduced concurrent consumers to avoid overwhelming vLLM
    concurrent_consumers: int = Field(default=3, alias="CONCURRENT_CONSUMERS_PER_WORKER")
    # Reduced prefetch to avoid queueing too many messages
    prefetch_count: int = Field(default=1, alias="PREFETCH_COUNT")
    
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


class ScraperSettings(BaseSettings):
    """Web scraping configuration."""
    
    request_delay_min: float = Field(default=2.0, alias="REQUEST_DELAY_MIN")
    request_delay_max: float = Field(default=5.0, alias="REQUEST_DELAY_MAX")
    request_timeout: int = Field(default=30, alias="REQUEST_TIMEOUT")
    user_agent: str = Field(
        default="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
        alias="USER_AGENT"
    )
    max_retries: int = Field(default=3, alias="MAX_RETRIES")
    max_pages: int = Field(default=10000, alias="MAX_PAGES")
    
    # BeautifulSoup extraction feature flags
    use_bs_extractors: bool = Field(default=False, alias="USE_BS_EXTRACTORS")
    bs_fallback_to_llm: bool = Field(default=True, alias="BS_FALLBACK_TO_LLM")
    use_bs_extractors_for_raw: str = Field(
        default="",
        alias="USE_BS_EXTRACTORS_FOR"
    )
    
    # LLM validation settings
    enable_llm_validation: bool = Field(default=True, alias="ENABLE_LLM_VALIDATION")
    llm_validation_blocking: bool = Field(default=False, alias="LLM_VALIDATION_BLOCKING")
    
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    
    @property
    def use_bs_extractors_for(self) -> List[str]:
        """Parse and return page types that should use BS extractors."""
        if isinstance(self.use_bs_extractors_for_raw, str):
            return [pt.strip() for pt in self.use_bs_extractors_for_raw.split(",") if pt.strip()]
        return []


class StorageSettings(BaseSettings):
    """Data storage configuration."""
    
    data_dir: str = Field(default="data/extracted", alias="DATA_DIR")
    logs_dir: str = Field(default="logs", alias="LOGS_DIR")
    
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


class TransfermarktSettings(BaseSettings):
    """Transfermarkt-specific configuration."""
    
    seed_urls_raw: str = Field(
        default="https://www.transfermarkt.com/premier-league/startseite/wettbewerb/GB1,https://www.transfermarkt.com/laliga/startseite/wettbewerb/ES1,https://www.transfermarkt.com/bundesliga/startseite/wettbewerb/L1,https://www.transfermarkt.com/serie-a/startseite/wettbewerb/IT1,https://www.transfermarkt.com/ligue-1/startseite/wettbewerb/FR1",
        alias="SEED_URLS"
    )
    
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore"
    )
    
    @property
    def seed_urls(self) -> List[str]:
        """Parse and return seed URLs as list."""
        if isinstance(self.seed_urls_raw, str):
            return [url.strip() for url in self.seed_urls_raw.split(",") if url.strip()]
        return []
    
    @property
    def seeds(self) -> List[str]:
        """Get seed URLs as list (alias for seed_urls)."""
        return self.seed_urls


class Settings(BaseSettings):
    """Master settings aggregator."""
    
    rabbitmq: RabbitMQSettings = Field(default_factory=RabbitMQSettings)
    vllm: VLLMSettings = Field(default_factory=VLLMSettings)
    queues: QueueSettings = Field(default_factory=QueueSettings)
    workers: WorkerSettings = Field(default_factory=WorkerSettings)
    scraper: ScraperSettings = Field(default_factory=ScraperSettings)
    storage: StorageSettings = Field(default_factory=StorageSettings)
    transfermarkt: TransfermarktSettings = Field(default_factory=TransfermarktSettings)
    
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


# Global settings instance
settings = Settings()
