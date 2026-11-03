from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


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


settings = Settings()
