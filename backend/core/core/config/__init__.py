from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings

from core.config.coordination import CoordinationPlatformDefaults
from core.config.database import DatabaseConfig
from core.config.intelligence import IntelligenceConfig
from core.config.memory import MemoryConfig
from core.config.redis import RedisConfig
from core.config.vendors.anthropic import AnthropicConfig
from core.config.vendors.aws import AWSConfig
from core.config.vendors.azure import AzureConfig
from core.config.vendors.centrifugo import CentrifugoConfig
from core.config.vendors.clerk import ClerkConfig
from core.config.vendors.ollama import OllamaConfig
from core.config.worker import WorkerConfig


class Settings(BaseSettings):
    # ContractNet constants remain flat and uppercase for backward compatibility.
    RESERVATION_TTL_SECONDS: int = 30
    BID_W_SKILL: float = 0.80
    BID_W_INFLUENCE: float = 0.20
    BID_INFLUENCE_K: float = 2.0
    SKILL_DECAY_RATE: float = (
        0.02  # per task completion in execute_task Phase 6 — recalibrate for target throughput
    )
    INFLUENCE_EMA_ALPHA: float = 0.15
    # Fraction of the executing agent's quality score credited to the CFP initiator.
    # Lower than 1.0 because the initiator routed the task but did not structure or execute it.
    CFP_COORDINATOR_CREDIT: float = 0.5
    # Sweeper thresholds — tasks stuck in these states longer than the timeout are cleaned up.
    TASK_OPEN_TIMEOUT_SECONDS: int = 600  # 10 min — stuck-open → expired
    TASK_RESERVED_TIMEOUT_SECONDS: int = 120  # 2 min  — stale reservation → re-open

    # ------------------------------------------------------------------ #
    # Domain sub-configs — each reads its own env_prefix independently.   #
    # ------------------------------------------------------------------ #
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    redis: RedisConfig = Field(default_factory=RedisConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    intelligence: IntelligenceConfig = Field(default_factory=IntelligenceConfig)
    coordination: CoordinationPlatformDefaults = Field(default_factory=CoordinationPlatformDefaults)
    anthropic: AnthropicConfig = Field(default_factory=AnthropicConfig)
    azure: AzureConfig = Field(default_factory=AzureConfig)
    aws: AWSConfig = Field(default_factory=AWSConfig)
    ollama: OllamaConfig = Field(default_factory=OllamaConfig)
    clerk: ClerkConfig = Field(default_factory=ClerkConfig)
    centrifugo: CentrifugoConfig = Field(default_factory=CentrifugoConfig)
    worker: WorkerConfig = Field(default_factory=WorkerConfig)


settings = Settings()
