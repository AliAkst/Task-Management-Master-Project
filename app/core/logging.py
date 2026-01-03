import logging
import sys

from app.config import settings


def setup_logging():
    """Uygulamanin genel log tasarimi burdadir"""

    # log seviyesi kodlari
    log_level = logging.DEBUG if settings.debug else logging.INFO
    log_format = (
        "%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d | %(message)s"
    )

    logging.basicConfig(
        level=log_level, format=log_format, handlers=[logging.StreamHandler(sys.stdout)]
    )
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("aiosqlite").setLevel(logging.WARNING)


def get_logger(
    name: str,
):
    return logging.getLogger(name)
