import json
from datetime import datetime
from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    DateTime,
    Float,
    Text,
    Boolean,
)
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.types import TypeDecorator

from app.services.config_manager import DATA_DIR

# --- Database Setup ---
DB_FILE = DATA_DIR / "rebalancer.db"
DATABASE_URL = f"sqlite:///{DB_FILE}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},  # Needed for SQLite with FastAPI
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# --- Custom JSON Type for SQLite ---
class Json(TypeDecorator):
    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None:
            return json.dumps(value)
        return value

    def process_result_value(self, value, dialect):
        if value is not None:
            return json.loads(value)
        return value


# --- SQLAlchemy Models ---


class RebalanceRun(Base):
    """
    Represents a historical record of a single rebalancing run.
    """

    __tablename__ = "rebalance_runs"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(String, unique=True, index=True, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    status = Column(String, nullable=False)
    is_dry_run = Column(Boolean, nullable=False)

    total_value_usd_before = Column(Float, nullable=True)
    total_value_usd_after = Column(Float, nullable=True)

    summary_message = Column(String, nullable=False)

    # Store the list of trades and errors as JSON strings
    trades_executed = Column(Json, nullable=True)
    errors = Column(Json, nullable=True)


# --- DB Initialization ---
def init_db():
    """Creates the database tables."""
    DATA_DIR.mkdir(exist_ok=True)
    Base.metadata.create_all(bind=engine)


def get_db():
    """FastAPI dependency to get a DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
