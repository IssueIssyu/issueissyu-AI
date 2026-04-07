from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker

from pgvector.sqlalchemy import register_vector

from app.core.config import settings


Base = declarative_base()


engine = create_engine(
    settings.sync_database_url,
    pool_pre_ping=True,
)

register_vector(engine)


SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


def get_db_session() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
