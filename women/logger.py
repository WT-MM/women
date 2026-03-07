"""Color logging for the women package."""

import logging
import sys

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BLUE = "\033[34m"
MAGENTA = "\033[35m"
CYAN = "\033[36m"

LEVEL_COLORS = {
    logging.DEBUG: DIM,
    logging.INFO: CYAN,
    logging.WARNING: YELLOW,
    logging.ERROR: RED,
    logging.CRITICAL: BOLD + RED,
}


class ColorFormatter(logging.Formatter):
    """Minimal color formatter for terminal output."""

    def format(self, record: logging.LogRecord) -> str:
        color = LEVEL_COLORS.get(record.levelno, RESET)
        level = record.levelname.lower()
        return f"{color}{BOLD}{level}{RESET} {record.getMessage()}"


def get_logger(name: str = "women") -> logging.Logger:
    """Get a configured color logger."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(ColorFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger
