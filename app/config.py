from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv


load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    environment: str = os.getenv("SUTRA_ENV", "development")
    database_url: str = os.getenv("SUTRA_DATABASE_URL", "sqlite:///./sutra.db")
    host: str = os.getenv("SUTRA_HOST", "127.0.0.1")
    port: int = int(os.getenv("SUTRA_PORT", "8000"))
    cors_origins: tuple[str, ...] = tuple(
        item.strip() for item in os.getenv(
            "SUTRA_CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
        ).split(",") if item.strip()
    )
    dev_auth: bool = os.getenv("SUTRA_DEV_AUTH", "true").lower() == "true"
    max_request_bytes: int = int(os.getenv("SUTRA_MAX_REQUEST_BYTES", "1048576"))
    rate_limit_per_minute: int = int(os.getenv("SUTRA_RATE_LIMIT_PER_MINUTE", "120"))
    protocol_path: Path = Path(os.getenv("SUTRA_PROTOCOL_PATH", "protocols/demo_wetlab.yaml"))

    # MongoDB Settings
    mongodb_url: str = os.getenv("SUTRA_MONGODB_URL", "mongodb://localhost:27017")
    mongodb_db: str = os.getenv("SUTRA_MONGODB_DB", "sutra_db")
    mongodb_enabled: bool = os.getenv("SUTRA_MONGODB_ENABLED", "true").lower() == "true"
    mongodb_timeout_ms: int = int(os.getenv("SUTRA_MONGODB_TIMEOUT_MS", "3000"))

    # AI Engine Integration Settings
    ai_engine_dir: Path = Path(os.getenv("SUTRA_AI_ENGINE_DIR", str(BASE_DIR.parent / "sutra-ai-engine")))

    def __post_init__(self) -> None:
        if self.port < 1 or self.port > 65535:
            raise ValueError("SUTRA_PORT must be between 1 and 65535")
        if self.max_request_bytes < 1:
            raise ValueError("SUTRA_MAX_REQUEST_BYTES must be positive")
        if self.rate_limit_per_minute < 1:
            raise ValueError("SUTRA_RATE_LIMIT_PER_MINUTE must be positive")
        
        # Ensure protocol_path resolves properly even when run from outside the backend directory
        resolved_path = self.protocol_path
        if not resolved_path.is_absolute() and not resolved_path.exists():
            candidate = BASE_DIR / resolved_path
            if candidate.exists():
                resolved_path = candidate
        object.__setattr__(self, "protocol_path", resolved_path)


settings = Settings()
