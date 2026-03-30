import logging
import os


def setup_logger(level: str = "INFO", log_file: str = "logs/app.log") -> logging.Logger:
    os.makedirs("logs", exist_ok=True)

    logger = logging.getLogger("review_bot")
    logger.setLevel(level.upper())
    logger.handlers.clear()

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s"
    )

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger