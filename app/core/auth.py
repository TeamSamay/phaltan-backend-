import hashlib
import hmac
import secrets
from fastapi import Header, HTTPException
from sqlalchemy.orm import Session
from app.config import settings
from app.models.models import Device


def new_device_token() -> str:
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def validate_device_token(db: Session, device_id: str, token: str | None) -> None:
    if settings.dev_auth and not token:
        return
    device = db.get(Device, device_id)
    if not device or not token or not hmac.compare_digest(device.token_hash, token_hash(token)):
        raise HTTPException(status_code=401, detail={"code": "invalid_device_token", "message": "Valid X-Device-Token required"})


def rate_key(x_device_id: str | None = Header(default=None)) -> str:
    return x_device_id or "anonymous"
