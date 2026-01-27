import logging
import sys
from app.config import settings

class CorrelationIdFilter(logging.Filter):
    """
    Log kayitlarina correlation ID ekleyen filter.
    """
    def filter(self,record: logging.LogRecord)-> bool:
        """
        Her log kaydina correlation_id attribute'u ekler.

        Args:
            record: Log kaydi

        Returns:
            bool: Her zaman True 
        
        """
        # Circular import' u onlemek icin burda importluyoruz
        from app.core.correlation import get_correlation_id
        record.correlation_id = get_correlation_id() or "no-correlation-id"
        return True

def setup_logging():
    """Uygulamanin genel log tasarimi burdadir"""

    # log seviyesi kodlari
    log_level = logging.DEBUG if settings.debug else logging.INFO
    log_format = (
        "%(asctime)s | %(correlation_id)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d | %(message)s"
    )
    # Handler olusturulan, filter ve formatter eklenen kisim
    handler=logging.StreamHandler(sys.stdout)
    handler.addFilter(CorrelationIdFilter())
    handler.setFormatter(logging.Formatter(log_format))
    # Root logger'a filter
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.handlers.clear()
    root_logger.addHandler(handler)

    
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("aiosqlite").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

def get_logger(
    name: str,
):
    return logging.getLogger(name)
