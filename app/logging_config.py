"""Structured logging configuration."""

import logging
import sys


def setup_logging(level: int = logging.INFO) -> None:
    """Configure structured logging for the application."""
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.addHandler(handler)

    # Set library loggers to WARNING to reduce noise
    logging.getLogger("PyQt6").setLevel(logging.WARNING)
