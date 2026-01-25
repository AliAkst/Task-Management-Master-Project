"""
Docstring for services.task-api.app.core.resilience

Resilience Patterns: Retry, Circuit Breaker, Timeout, vb...

Bu modul uygulamayi hatalara karsi dayanikli hale getirir.

"""

import asyncio
from functools import wraps
from typing import Callable,Type

from tenacity import(
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    before_sleep_log,
    after_log
)
from app.core.logging import get_logger
from app.config import settings
import time
from enum import Enum
from dataclasses import dataclass

logger = get_logger(__name__)

RETRYABLE_EXCEPTIONS: tuple[Type[Exception],...]=(
    ConnectionError,
    TimeoutError,
    asyncio.TimeoutError,
    OSError,
)

def with_db_retry(func: Callable)-> Callable:
    """
    Database islemleri icin retry decorator.

    Kullanim:
        @with_db_retry
        async def get_user(user_id: int):
            return await db.query(...)
    Davranis:
        -Maksimum 3 deneme
        -Exponential Backoff(1sn,2sn,4sn)
        -Sadece gecici hatalar icin retry
        -Her retry loglanir.
    """
    @wraps(func)
    @retry(
        stop=stop_after_attempt(settings.retry_max_attempts), # settings kadar denemeyap
        wait=wait_exponential(
            multiplier=1,
            min=settings.retry_min_wait_seconds,
            max=settings.retry_max_wait_seconds
        ),
        retry=retry_if_exception_type(RETRYABLE_EXCEPTIONS),# Sadece bu hatalar için retry
        before_sleep=before_sleep_log(logger,log_level=20),#Her retry öncesi logla
        reraise=True # Son denemede de hata olursa fırlat
    )
    async def wrapper(*args,**kwargs):
        return await func(*args,**kwargs)
    
    return wrapper

def with_retry(
        max_attempts: int | None = None,
        min_wait: float | None = None,
        max_wait : float | None = None,
        retry_exceptions: tuple[Type[Exception], ...] | None = None
) ->Callable:
    """
    Ozellestirilebilir retry decorator.

    Kullanim:
        @with_retry(max_attempt=5,min _wait=0.5)
        async def call_external_api():
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        @retry(
            stop=stop_after_attempt(max_attempts or settings.retry_max_attempts),
            wait=wait_exponential(
                multiplier=1,
                min=min_wait or settings.retry_min_wait_seconds,
                max= max_wait or settings.retry_max_wait_seconds
            ),
            retry=retry_if_exception_type(retry_exceptions or RETRYABLE_EXCEPTIONS),
            before_sleep=before_sleep_log(logger,log_level=20),
            reraise=True
        )
        async def wrapper(*args,**kwargs):
            return await func(*args,**kwargs)
        
        return wrapper
    return decorator
def with_sync_retry(func: Callable) -> Callable:
    """
    Senkron fonksiyonlar icin retry decorator.

    Kullanim:
    @wuth_sync_retry
    def sync_operation():
        ...
    """
    @wraps(func)
    @retry(
        stop=stop_after_attempt(settings.retry_max_attempts),
        wait=wait_exponential(
            multiplier=1,
            min=settings.retry_min_wait_seconds,
            max=settings.retry_max_wait_seconds
        ),
        retry=retry_if_exception_type(RETRYABLE_EXCEPTIONS),
        before_sleep=before_sleep_log(logger,log_level=20),
        reraise=True
    )
    def wrapper(*args,**kwargs):
        return func(*args,**kwargs)
    
    return wrapper

# ______CIRCUIT BREAKER______

class CircuitState(Enum):
    """ Circuit Breaker Durumlari """
    CLOSED = "closed" #normal calisma
    OPEN = "open" # devre acik istekler reddedilir
    HALF_OPEN = "half_open" # Test Modu

class CircuitBreakerError(Exception):
    """Circuit acik oldugunda firlatilir."""
    pass

@dataclass
class CircuitStats:
    """Circuit Breaker Istatistikleri"""
    failure: int = 0
    successes: int = 0
    last_failure_time: float = 0
    state: CircuitState = CircuitState.CLOSED

class CircuitBreaker:
    """
    Circuit Breaker Pattern implementasyon classi 

    Kullanim:
        breaker = CircuitBreaker(failure_threshold=5,recovery_timeout=30)

        async with breaker:
            await risky_operation()

    Durumlar:
        CLOSED: Normal calisma, hatalari sayar sadece
        OPEN: Istekler aninda reddedilir.
        HALF_OPEN: Test modu 1 istek denenir.
    """

    def __init__(
            self,
            failure_threshold: int | None = None,
            recovery_timeout: int | None = None,
            half_open_max_calls: int | None = None,
            name: str = "default"
    ):
        self.failure_threshhold= failure_threshold or settings.circuit_breaker_failure_threshold
        self.recovery_timeout = recovery_timeout or settings.circuit_breaker_recovery_timeout
        self.half_open_max_calls = half_open_max_calls or settings.circuit_breaker_half_open_max_calls
        self.name= name

        self._stats=CircuitStats()
        self.half_open_calls=0
    @property
    def state(self)->CircuitState:
        """Mevcut durumu hesapla"""
        if self._stats.state == CircuitState.OPEN:
            # Recovery timeout gecti mi ?
            if time.time() - self._stats.last_failure_time >= self.recovery_timeout
                self._stats.state = CircuitState.HALF_OPEN
                self.half_open_calls = 0
                logger.info(f"Circuit'{self.name}' HALF_OPEN durumuna gecti.")
        
        return self._stats.state

    def _record_success(self):
        """Basarili cagriyi kaydeder."""
        if self.state == CircuitState.HALF_OPEN:
            self._stats.state = CircuitState.CLOSED
            self._stats.failure = 0
            logger.info(f"Circuit '{self.name}' CLOSED durumuna gecti (recovered)")

        self._stats.successes += 1
    
    def _record_failure(self):
        """Basarisiz cagriyi kaydeder."""
        self._stats.failure += 1
        self._stats.last_failure_time = time.time()
        
        if self.state == CircuitState.HALF_OPEN:
            #Half-Open'da hata ->tekrar ac
            self._stats.state = CircuitState.OPEN
            logger.warning(
                f"Circuit '{self.name}' OPEN durumuna gecti"
                f"({self._stats.failure} hata)"
            )
    
    async def __aenter__(self):
        """Context Manager Girisi"""
        if self.state == CircuitState.OPEN:
            raise CircuitBreakerError(
                f"Circuit '{self.name}' acik."
                f"{self.recovery_timeout}s sonra tekrar deneyin."
            )
        
        if self.state == CircuitState.HALF_OPEN:
            if self.half_open_calls >= self.half_open_max_calls:
                raise CircuitBreakerError(
                    f"Circuit '{self.name}'test modunda lutfen bekleyin."
                )
            
            self.half_open_calls += 1
        return self
    async def __aexit__(self,exc_type,exc_val,exc_tb):
        """Context Manager cikisi"""
        if exc_type is None:
            self._record_success()
        else:
            self._record_failure()
        
        return False # exception yok olmasin istedigimiz icin yaptik.
    
    def get_stats(self)-> dict:
        """Istatistikleri dondur."""
        return{
            "name":self.name,
            "state":self.state.value,
            "failure":self._stats.failure,
            "successes":self._stats.successes,
            "failure_threshold":self.failure_threshhold,
            "recovery_timeout":self.recovery_timeout
        }
    
# --- GLOBAL CIRCUIT BREAKERS ---
# Her servis icin ayri breaker
db_circuit_breaker = CircuitBreaker(name="database")
redis_circuit_breaker = CircuitBreaker(name="redis")


def with_circuit_breaker(breaker: CircuitBreaker):
    """
    Circuit Breaker decorator.

    Kullanim:
    @with_circuit_breaker(db_circuit_breaker)
    async def risky_db_operations():
        ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args,**kwargs):
            async with breaker:
                return await func(*args,**kwargs)
            return wrapper
        return decorator

def with_resiliance(
        breaker:CircuitBreaker | None = None,
        max_attempts: int | None = None,
        min_wait: float | None = None,
        max_wait: float | None = None,
)->Callable:
    """
    Retry + Circuit Breaker birlestiren decorator.
    
    Sira:
    1-Circuit Breaker kontrol(aciksa aninda reddet)
    2-Retry dene (kapaliysa)
    3- Tum retry'lar basarisizsa -> Circuit'e hata kaydet

    Kullanim:
    @with_resiliance(breaker=db_circuit_breaker, max attempts = 3)
    async def critical_operation():
        ...
    """
    def decorator(func: Callable) -> Callable:
        #Once retry decorator'i uygula
        retried_func = with_retry(
            max_attempts=max_attempts,
            min_wait=min_wait,
            max_wait=max_wait
        )(func)

        @wraps(func)
        async def wrapper(*args,**kwargs):
            if breaker:
                async with breaker:
                    return await retried_func(*args,**kwargs)
            else:
                return await retried_func(*args,**kwargs)
            return wrapper
        return decorator