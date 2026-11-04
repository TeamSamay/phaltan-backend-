from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings


class Base(DeclarativeBase):
    pass


_connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
_engine_options = {"connect_args": _connect_args, "pool_pre_ping": True}
if settings.database_url in {"sqlite://", "sqlite:///:memory:"}:
    _engine_options["poolclass"] = StaticPool
engine = create_engine(settings.database_url, **_engine_options)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from app.models import models  # noqa: F401
    Base.metadata.create_all(bind=engine)
