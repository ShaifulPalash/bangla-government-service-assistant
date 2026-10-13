## Structured logger
"""Logging setup: one JSON line per log message."""

# Imports
import json
import logging
import sys


# JsonFormatter class
class JsonFormatter(logging.Formatter):
    """Turns a log record into a single JSON line."""

    def format(self, record: logging.LogRecord) -> str:
        # Build the JSON payload
        payload = {
            "time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        # Include exception details
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)
        # ensure_ascii=False keeps Unicode characters readable,
        # which is particularly useful if application logs Bengali text


# setup_logging() function
def setup_logging(level: str = "INFO") -> None:
    """Configure the root logger once, at application start."""
    handler = logging.StreamHandler(sys.stdout)  # Create a console handler
    handler.setFormatter(JsonFormatter())  # Attach the JSON formatter

    # Configure the root logger
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())
