import os
import sys
import logging
from logging.handlers import RotatingFileHandler

def setup_logging(level_name: str = "INFO", log_file_path: str = "KnowledgeBase/harvester.log") -> logging.Logger:
    os.makedirs(os.path.dirname(os.path.abspath(log_file_path)), exist_ok=True)

    # Map logging levels
    level = getattr(logging, level_name.upper(), logging.INFO)

    logger = logging.getLogger("harvester")
    logger.setLevel(level)

    # Clear existing handlers
    if logger.handlers:
        logger.handlers.clear()

    formatter = logging.Formatter(
        '{"timestamp": "%(asctime)s", "level": "%(levelname)s", "module": "%(module)s", "message": "%(message)s"}'
    )

    # Rotating file handler
    file_handler = RotatingFileHandler(
        log_file_path, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(level)
    logger.addHandler(file_handler)

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(module)s: %(message)s')
    console_handler.setFormatter(console_formatter)
    console_handler.setLevel(level)
    logger.addHandler(console_handler)

    return logger

def get_logger() -> logging.Logger:
    return logging.getLogger("harvester")
