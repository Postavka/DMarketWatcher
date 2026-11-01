from pathlib import Path

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Base


def make_engine(url: str = "sqlite:///data/market.db") -> Engine:
    if url.startswith("sqlite:///") and ":memory:" not in url:
        Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
    return create_engine(url)


def init_db(engine: Engine) -> sessionmaker[Session]:
    # create_all while the schema is still moving; switch to Alembic migrations once it settles.
    Base.metadata.create_all(engine)
    return sessionmaker(engine, expire_on_commit=False)
