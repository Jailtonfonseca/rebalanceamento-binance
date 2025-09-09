import logging
import json
from logging.handlers import RotatingFileHandler

from app.services.config_manager import DATA_DIR

LOGS_DIR = DATA_DIR / "logs"


class JsonFormatter(logging.Formatter):
    """Formats log records as a JSON string.

    This formatter converts a log record into a JSON object, making it suitable for
    structured logging environments like ELK stacks or cloud-based logging services.
    """

    def format(self, record: logging.LogRecord) -> str:
        """Formats a log record into a JSON string.

        Args:
            record: The log record to format.

        Returns:
            A JSON string representing the log record.
        """
        log_object = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "message": record.getMessage(),
            "module": record.module,
            "funcName": record.funcName,
            "lineNo": record.lineno,
        }
        # Include exception info if it exists
        if record.exc_info:
            log_object["exc_info"] = self.formatException(record.exc_info)

        return json.dumps(log_object)


def setup_logging():
    """Configures structured JSON logging for the application.

    This function sets up the root logger to output logs in a structured
    JSON format to a rotating file, and to the console with a standard
    human-readable format. It ensures that the log directory exists and
    configures log rotation to manage file size.
    """
    LOGS_DIR.mkdir(exist_ok=True)
    log_file = LOGS_DIR / "app.log"

    # Get the root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    # Remove any existing handlers to avoid duplicates
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Create a rotating file handler for JSON logs
    file_handler = RotatingFileHandler(
        log_file, maxBytes=10 * 1024 * 1024, backupCount=5
    )  # 10MB per file, 5 backups
    file_handler.setFormatter(JsonFormatter())

    # Create a stream handler for console output (optional, but good for dev)
    # Using a standard formatter for console for better readability
    console_handler = logging.StreamHandler()
    console_formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    console_handler.setFormatter(console_formatter)

    # Add handlers to the root logger
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    logging.info("Logging configured successfully.")


def get_logger(name: str) -> logging.Logger:
    """Gets a logger instance configured by the application setup.

    This is a helper function to obtain a logger that is part of the
    application's logging hierarchy.

    Args:
        name: The name of the logger to retrieve. Typically __name__.

    Returns:
        An instance of logging.Logger.
    """
    return logging.getLogger(name)
