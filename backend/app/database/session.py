from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from ..core.config import get_settings
url=get_settings().database_url
engine=create_engine(url, connect_args={"check_same_thread": False} if url.startswith("sqlite") else {}, pool_pre_ping=True)
SessionLocal=sessionmaker(bind=engine, expire_on_commit=False)
def get_db():
    with SessionLocal() as session: yield session
