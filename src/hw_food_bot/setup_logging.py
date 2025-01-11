import logging
import sys


def setup_logging(level: str | None = None) -> None:
    """Setup logging configuration for the entire application."""

    log_level = getattr(logging, level.upper()) if level else logging.INFO

    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=log_level,
        handlers=[
            logging.StreamHandler(sys.stdout),
        ],
    )

    logging.getLogger("httpx").setLevel(logging.WARNING)

    logging.getLogger("hw_food_bot").setLevel(log_level)
