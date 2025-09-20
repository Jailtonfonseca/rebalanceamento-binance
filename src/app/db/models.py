"""Database models and session management for the application.

This module defines the SQLAlchemy ORM models for the application's data,
sets up the database engine and session management, and provides helper
functions for database initialization and dependency injection.
"""

import json
from datetime import datetime, timezone
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
from sqlalchemy.orm import sessionmaker, declarative_base, validates
from sqlalchemy.types import TypeDecorator
from sqlalchemy.engine import Dialect

from app.services.config_manager import DATA_DIR
from app.utils.time import utc_now

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
    """A custom SQLAlchemy type to store JSON data in a TEXT column.

    This class handles the serialization of Python objects to JSON strings
    when writing to the database, and deserialization from JSON strings back
    to Python objects when reading from the database. It is designed to work
    with SQLite, which does not have a native JSON type.
    """

    impl = Text
    cache_ok = True

    def process_bind_param(
        self, value: dict | list | None, dialect: Dialect
    ) -> str | None:
        """Serializes a Python object to a JSON string for database storage.

        Args:
            value: The Python object to serialize.
            dialect: The SQLAlchemy dialect in use.

        Returns:
            A JSON formatted string, or None if the value is None.
        """
        if value is not None:
            return json.dumps(value)
        return value

    def process_result_value(
        self, value: str | None, dialect: Dialect
    ) -> dict | list | None:
        """Deserializes a JSON string from the database into a Python object.

        Args:
            value: The JSON string from the database.
            dialect: The SQLAlchemy dialect in use.

        Returns:
            A Python dictionary or list, or None if the value is None.
        """
        if value is not None:
            return json.loads(value)
        return value


# --- SQLAlchemy Models ---


class RebalanceRun(Base):
    """Represents a historical record of a single rebalancing run.

    This model stores comprehensive details about each execution of the
    rebalancing logic, including its status, timing, outcomes, and any
    associated data like trades or errors.
    """

    __tablename__ = "rebalance_runs"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(String, unique=True, index=True, nullable=False)
    timestamp = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    status = Column(String, nullable=False)
    is_dry_run = Column(Boolean, nullable=False)

    total_value_usd_before = Column(Float, nullable=True)
    total_value_usd_after = Column(Float, nullable=True)

    summary_message = Column(String, nullable=False)

    # Store the list of trades and errors as JSON strings
    trades_executed = Column(Json, nullable=True)
    errors = Column(Json, nullable=True)
    projected_balances = Column(Json, nullable=True)
    total_fees_usd = Column(Float, nullable=True)

    @validates("timestamp")
    def _ensure_timezone(self, key: str, value: datetime | None) -> datetime | None:
        """Normalise timestamps to UTC-aware datetimes."""

        if value is None:
            return value

        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)

        return value.astimezone(timezone.utc)


# --- DB Initialization ---
def init_db():
    """Initializes the database and creates tables if they don't exist.

    This function ensures that the data directory exists and then creates all
    tables defined by the SQLAlchemy Base metadata. It should be called on
    application startup.
    """
    DATA_DIR.mkdir(exist_ok=True)
    Base.metadata.create_all(bind=engine)


def get_db():
    """A FastAPI dependency to provide a database session per request.

    This generator function creates a new SQLAlchemy session for each incoming
    request, yields it to the endpoint, and ensures that the session is
    closed after the request is finished, even if an error occurs.

    Yields:
        An active SQLAlchemy session.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
