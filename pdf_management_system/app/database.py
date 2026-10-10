from datetime import datetime, timezone
from typing import Generator, Optional

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from app.config import DATABASE_URL

# Handle sqlite fallback for local testing if postgres is not immediately running
db_url = DATABASE_URL
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

engine = create_engine(
    db_url,
    pool_pre_ping=True,
    pool_recycle=300,
    connect_args={"connect_timeout": 5} if db_url.startswith("postgresql") else {},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class UserActivity(Base):
    __tablename__ = "user_activity"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(String(128), default="anonymous", index=True)
    action = Column(String(64), nullable=False, index=True)  # UPLOAD, DOWNLOAD, DELETE, CREATE_FOLDER, SYNC_S3
    filename = Column(String(512), nullable=True)
    storage_type = Column(String(32), default="s3")  # s3, local
    file_size_bytes = Column(BigInteger, nullable=True)
    ip_address = Column(String(64), nullable=True)
    user_agent = Column(Text, nullable=True)
    details = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)


def init_db() -> None:
    try:
        Base.metadata.create_all(bind=engine)
        print("Database initialized successfully.")
    except Exception as e:
        print(f"Database initialization warning (will retry on query): {e}")


def get_db() -> Generator[Session, None, None]:
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def log_activity(
    action: str,
    filename: Optional[str] = None,
    user_id: str = "anonymous",
    storage_type: str = "s3",
    file_size_bytes: Optional[int] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    details: Optional[str] = None,
) -> None:
    try:
        with SessionLocal() as db:
            record = UserActivity(
                action=action,
                filename=filename,
                user_id=user_id,
                storage_type=storage_type,
                file_size_bytes=file_size_bytes,
                ip_address=ip_address,
                user_agent=user_agent,
                details=details,
                created_at=datetime.now(timezone.utc),
            )
            db.add(record)
            db.commit()
    except Exception as e:
        # Avoid failing the main user operation if activity logging encounters a DB issue
        print(f"[Activity Logging Error] Failed to log activity '{action}' for file '{filename}': {e}")
