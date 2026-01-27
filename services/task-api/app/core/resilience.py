"""
Docstring for services.task-api.app.core.resilience

Resilience Patterns: Retry, Circuit Breaker, Timeout, vb...

Bu modul uygulamayi hatalara karsi dayanikli hale getirir.

"""

from ast import Call
import asyncio
from functools import wraps
from math import log
from sys import exception
from tkinter import NO
from typing import Callable, Type, Any

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
from app.core.exceptions import CircuitBreakerError,BulkheadFullError

logger = get_logger(__name__)

RETRYABLE_EXCEPTIONS: tuple[Type[Exception], ...] = (
    ConnectionError,
    TimeoutError,
    asyncio.TimeoutError,
    OSError,
)

def with_db_retry(func: Callable) -> Callable:
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
        retry=retry_if_exception_type(RETRYABLE_EXCEPTIONS), # Sadece bu hatalar için retry
        before_sleep=before_sleep_log(logger, log_level=20), # Her retry öncesi logla
        reraise=True # Son denemede de hata olursa fırlat
    )
    async def wrapper(*args, **kwargs):
        return await func(*args, **kwargs)
    
    return wrapper

def with_retry(
        max_attempts: int | None = None,
        min_wait: float | None = None,
        max_wait: float | None = None,
        retry_exceptions: tuple[Type[Exception], ...] | None = None
) -> Callable:
    """
    Ozellestirilebilir retry decorator.

    Kullanim:
        @with_retry(max_attempts=5, min_wait=0.5)
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
                max=max_wait or settings.retry_max_wait_seconds
            ),
            retry=retry_if_exception_type(retry_exceptions or RETRYABLE_EXCEPTIONS),
            before_sleep=before_sleep_log(logger, log_level=20),
            reraise=True
        )
        async def wrapper(*args, **kwargs):
            return await func(*args, **kwargs)
        
        return wrapper
    return decorator

def with_sync_retry(func: Callable) -> Callable:
    """
    Senkron fonksiyonlar icin retry decorator.

    Kullanim:
        @with_sync_retry
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
        before_sleep=before_sleep_log(logger, log_level=20),
        reraise=True
    )
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)
    
    return wrapper

# ______CIRCUIT BREAKER______

class CircuitState(Enum):
    """ Circuit Breaker Durumlari """
    CLOSED = "closed" # normal calisma
    OPEN = "open" # devre acik istekler reddedilir
    HALF_OPEN = "half_open" # Test Modu

@dataclass
class CircuitStats:
    """Circuit Breaker Istatistikleri"""
    failures: int = 0
    successes: int = 0
    last_failure_time: float = 0
    state: CircuitState = CircuitState.CLOSED

class CircuitBreaker:
    """
    Circuit Breaker Pattern implementasyon classi 

    Kullanim:
        breaker = CircuitBreaker(failure_threshold=5, recovery_timeout=30)

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
        self.failure_threshold = failure_threshold or settings.circuit_breaker_failure_threshold
        self.recovery_timeout = recovery_timeout or settings.circuit_breaker_recovery_timeout
        self.half_open_max_calls = half_open_max_calls or settings.circuit_breaker_half_open_max_calls
        self.name = name

        self._stats = CircuitStats()
        self.half_open_calls = 0
    
    @property
    def state(self) -> CircuitState:
        """Mevcut durumu hesapla"""
        if self._stats.state == CircuitState.OPEN:
            # Recovery timeout gecti mi ?
            if time.time() - self._stats.last_failure_time >= self.recovery_timeout:
                self._stats.state = CircuitState.HALF_OPEN
                self.half_open_calls = 0
                logger.info(f"Circuit'{self.name}' HALF_OPEN durumuna gecti.")
        
        return self._stats.state

    def _record_success(self):
        """Basarili cagriyi kaydeder."""
        if self.state == CircuitState.HALF_OPEN:
            self._stats.state = CircuitState.CLOSED
            self._stats.failures = 0
            logger.info(f"Circuit '{self.name}' CLOSED durumuna gecti (recovered)")

        self._stats.successes += 1
    
    def _record_failure(self):
        """Basarisiz cagriyi kaydeder."""
        self._stats.failures += 1
        self._stats.last_failure_time = time.time()
        
        if self.state == CircuitState.HALF_OPEN:
            # Half-Open'da hata -> tekrar ac
            self._stats.state = CircuitState.OPEN
            logger.warning(
                f"Circuit '{self.name}' OPEN durumuna gecti "
                f"({self._stats.failures} hata)"
            )
        elif self._stats.failures >= self.failure_threshold:
            self._stats.state = CircuitState.OPEN
            logger.warning(
                f"Circuit '{self.name}' OPEN durumuna gecti "
                f"({self._stats.failures} hata)"
            )
    
    async def __aenter__(self):
        """Context Manager Girisi"""
        if self.state == CircuitState.OPEN:
            raise CircuitBreakerError(self.name, self.recovery_timeout)
        
        if self.state == CircuitState.HALF_OPEN:
            if self.half_open_calls >= self.half_open_max_calls:
                raise CircuitBreakerError(
                    f"Circuit '{self.name}' test modunda lutfen bekleyin."
                )
            
            self.half_open_calls += 1
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context Manager cikisi"""
        if exc_type is None:
            self._record_success()
        else:
            self._record_failure()
        
        return False # exception yok olmasin istedigimiz icin yaptik.
    
    def get_stats(self) -> dict:
        """Istatistikleri dondur."""
        return {
            "name": self.name,
            "state": self.state.value,
            "failure": self._stats.failures,
            "successes": self._stats.successes,
            "failure_threshold": self.failure_threshold,
            "recovery_timeout": self.recovery_timeout
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
        async def wrapper(*args, **kwargs):
            async with breaker:
                return await func(*args, **kwargs)
        return wrapper
    return decorator

def with_resilience(
        breaker: CircuitBreaker | None = None,
        max_attempts: int | None = None,
        min_wait: float | None = None,
        max_wait: float | None = None,
        timeout: float | None = None,
        bulkhead:Bulkhead | None = None
) -> Callable:
    """
    Retry + Circuit Breaker + Timeout + Bulkhead birlestiren decorator.
    
    Sira(disdan ice):
    1-Bulkhead(slot al, yoksa reddet)
    2-Timeout kontrol (sure asilirsa hemen hata)
    3-Circuit Breaker kontrol(aciksa aninda reddet)
    4-Retry  (Hata olursa tekrar dene)
    5- Orjinal Fonksiyon

    Kullanim:
        @with_resiliance(
            breaker=db_circuit_breaker,
            bulkhead=db_bulkhead,
            max_attempts=3,
            timeout=5.0,
        )
        async def critical_operation():
            ...
    """
    def decorator(func: Callable) -> Callable:
        retried_func = with_retry(
            max_attempts=max_attempts,
            min_wait=min_wait,
            max_wait=max_wait
        )(func)

        @wraps(func)
        async def wrapper(*args, **kwargs):
            async def execute():
                if breaker:
                    async with breaker:
                        return await retried_func(*args, **kwargs)
                else:
                    return await retried_func(*args, **kwargs)
            async def with_timeout_wrapper():
                if timeout:
                    try:
                        return await asyncio.wait_for(execute(), timeout=timeout)
                    except asyncio.TimeoutError:
                        logger.error(
                            f"Timeout: {func.__name__} {timeout}s icinde tamamlanamadi."
                        )
                        raise
                else:
                    return await execute()
        
            #Bulkhead
            if bulkhead:
                async with bulkhead:
                    return await with_timeout_wrapper()
            else:
                return await with_timeout_wrapper()
        return wrapper
    return decorator

# --- TIMEOUT PATTERN ---
class TimeoutConfig:
    """
    Timeout sureleri icin merkezi yapilandirma.
    """
    DB=settings.db_timeout_seconds
    EXTERNAL_API=settings.external_api_timeout_seconds
    DEFAULT=settings.default_timeout_seconds
def with_timeout(seconds: float | None = None):
    """
    Async fonksiyonlara timeout ekleyen decorator
    
    Amaci ne:
        1-Maksimum bekleme suresi tanimlama
        2-Farkli islemler icin farkli timeoutlar atayabilme
    
    Kullanim:
        @with_timeout(5.0)
        async def slow_operation():
            ...
        @with_timeout(TimeoutConfig.DB)
        async db_operation():
            ...
    
    Args:
        seconds:Timeout suresi (saniye). None ise default kullanilir
    
    Raises:
        asyncio.TimeoutError: Sure asilirsa
    """
    def decorator(func: Callable)->Callable:
        @wraps(func)
        async def wrapper(*args,**kwargs):
            timeout = seconds or settings.default_timeout_seconds
            try:
                return await asyncio.wait_for(
                    func(*args,**kwargs),
                    timeout=timeout
                )
            except asyncio.TimeoutError:
                logger.error(
                    f"Timeout: {func.__name__}{timeout}s icinde tamamlanamadi."
                )
                raise
        return wrapper
    return decorator

# --- BULKHEAD PATTERN ---
class Bulkhead:
    """
    Bulkhead Pattern implementasyonu

    Burda amacimiz her bir kismin kendine ait bir kaynagi olsun boylelikle biri haddini asinca hepsi patlamasin.
    
    Kullanim:
        db_bulkhead = Bulkhead(max_concurrent=10, name= "database")

        async with db_bulkhead:
            await db_operation()
    """

    def __init__(
        self,
        max_concurrent: int = 10,
        timeout: float | None = None,
        name: str = "default"
    ):
        self.max_concurrent = max_concurrent
        self.timeout= timeout
        self.name=name
        self._semaphore=asyncio.Semaphore(max_concurrent)
        self._active_count = 0
    
    @property
    def active_count(self)-> int:
        """Su an aktif olan istek sayisi"""
        return self._active_count 
    
    @property
    def available_slots(self)-> int:
        """Kullanilabilir slot sayisi"""
        return self.max_concurrent - self._active_count
    
    async def __aenter__(self):
        """Context Manager girisi - slot alarak girer."""
        if self.timeout is not None:
            try:
                await asyncio.wait_for(
                    self._semaphore.acquire(),
                    timeout=self.timeout
                )
            except asyncio.TimeoutError:
                raise BulkheadFullError(
                    self.name,
                    self.active_count,
                    self.max_concurrent
                )
        else:
            if self._semaphore.locked():
                raise BulkheadFullError(
                    self.name,
                    self._active_count,
                    self.max_concurrent
                )
            await self._semaphore.acquire()
        
        self._active_count += 1
        logger.debug(
            f"Bulkhead '{self.name}': Slot alindi."
            f"({self.active_count}/{self.max_concurrent})"
        )
        return self
    
    async def __aexit__(self,exc_type,exc_val,exc_tb):
        """Context Manager cikisi - slot biraktigi kisim"""
        self._active_count -= 1
        self._semaphore.release()
        logger.debug(
            f"Bulkhead '{self.name}': Slot Birakildi"
            f"({self._active_count}/{self.max_concurrent})"
        )
        return False


    def get_stats(self) -> dict:
        """Bulkhead istatistikleri"""
        return {
            "name":self.name,
            "max_concurrent":self.max_concurrent,
            "active_count":self._active_count,
            "available_slots":self.available_slots,
            "timeout": self.timeout
        }

# --- GLOBAL BULKHEADS ---

db_bulkhead = Bulkhead(max_concurrent=10, timeout=5.0, name="database")
redis_bulkhead=Bulkhead(max_concurrent=50,timeout=1.0,name="redis")
external_api_bulkhead = Bulkhead(max_concurrent=10, timeout=10.0, name="external_api") 

# Bulkhead Decorator

def with_bulkhead(bulkhead: Bulkhead):
    """
    Bulkhead decorator.

    Kullanim:
        @with_bulkhead(db_bulkhead)
        async def db_query():
            ...
    """
    def decorator(func:Callable)-> Callable:
        @wraps(func)
        async def wrapper(*args,**kwargs):
            async with bulkhead:
                return await func(*args,**kwargs)
        return wrapper
    return decorator

# ---GRACEFUL DEGRATION ---

def with_fallback(
    fallback_func: Callable | None = None,
    default_value: Any = None,
    exceptions: tuple[Type[Exception], ...] = (Exception,)
):
    """
    Graceful Degradation decorator - Hata durumunda fallback calistirir.(cache hata verirse db den cek !!)\
    
    Kullanim:
        # Fallback fonksiyon ile:
        @with_fallback(fallback_func= get_from_database)
        async def get_from_cache(key: str):
            return await redis.get(key))
        
        # Default deger ile:
        @with_fallback(default_value=[])
        async def get_reccomendations():
            return await ai_service_recommend()
    
    Args:
        fallback_func: Hata durumunda cagrulacak alternatif fonksiyon
        default_value: Fallback yoksa dondurulecek varsayilan deger
        exceptions: Hangi exception'larda fallback calissin
    """
    def decorator(func: Callable)-> Callable:
        @wraps(func)
        async def wrapper(*args,**kwargs):
            try:
                return await func(*args,**kwargs)
            except exceptions as e:
                logger.warning(
                    f"Degradation: {func.__name__}basarisiz oldu ({type(e).__name__})."
                    f"Fallback Kullaniliyor."
                )

                # Once fallback fonksiyonunu dene
                if fallback_func is not None:
                    try:
                        if asyncio.iscoroutinefunction(fallback_func):
                            return await fallback_func(*args,**kwargs)
                        else:
                            return fallback_func(*args,**kwargs)
                    except Exception as fallback_error:
                        logger.error(
                            f"fallback basarisiz : {fallback_error}"
                        )
                
                # Fallback da basarisizsa default deger donuyoruz.
                if default_value is not None:
                    logger.info(f"Default deger donuluyor: {default_value}")
                    return default_value
                
                # Hicbiri de yoksa mecbur orjinal hatayi gonderiyoruz(umarim prodda bu yasanmaz.)
                raise
        return wrapper
    return decorator

class FeatureFlag:
    """
    Feature Flag sistemi - Ozellikleri dinamik olarak acip kapatmaya yarar.

    Kullanim:
    cache_flag = FeatureFlag("cache", settings.feature_cache_enabled)

    if cache_flag_enabled():
        return await get_from_cache()
    else:
        return await get_from_database()
    """

    _flags: dict[str,bool] = {} # Global Flag storage

    def __init__(self,name : str,default_enabled: bool= True):
        self.name = name
        if name not in FeatureFlag._flags:
            FeatureFlag._flags[name] = default_enabled
    
    def is_enabled(self) -> bool:
        """flag aktif mi ?"""
        return FeatureFlag._flags.get(self.name, True)
    
    def enable(self):
        """Flag'i aktif et"""
        FeatureFlag._flags[self.name]=True
        logger.info(f"Feature '{self.name}' ENABLED")
    
    def disable(self):
        """Flag'i devre disi birak"""
        FeatureFlag._flags[self.name]= False
        logger.info(f"Feature '{self.name}'DISABLED")
    
    @classmethod
    def get_all_flags(cls) -> dict[str,bool]:
        """Tum flag'lerin durumunu dondurur."""
        return cls._flags.copy()

# ----- GLOBAL FEATURE FLAGS -----
cache_feature = FeatureFlag("cache",settings.feature_cache_enabled)
ai_feature = FeatureFlag("ai_suggestions",settings.feature_ai_suggestions_enabled)
notifications_feature = FeatureFlag("notifications",settings.feature_notifications_enabled)

def with_feature_flag(
    flag: FeatureFlag,
    disable_return: Any = None,
    fallback_func: Callable | None =None
):
    """
    Feature Flag Decorator - Flag kapaliysa fonksiyon calismaz.

    Kullanim:
        @with_feature_flag(cache_feature, fallback_func= get_from_db)
        async def get_from_cache(key: str):
            return await redis.get(key)
        
        @with_feature_flag(ai_feature, disable_return=[])
        async def get_ai_recommendations():
            return await ai_service.recommend()
    
    Args:
        flag: Kontrol edilecek FeatureFlag
        disabled_return: Flag kapaliyken dondurulecek deger
        fallback_func: Flag kapaliyken cagrilacak alternatif fonksiyon
    """
    def decorator(func: Callable)->Callable:
        @wraps(func)
        async def wrapper(*args,**kwargs):
            if not flag.is_enabled():
                logger.debug(
                    f"Feature '{flag.name} devre disi.'"
                    f"{func.__name__} atlaniyor."
                )

                if fallback_func is not None:
                    if asyncio.iscoroutinefunction(fallback_func):
                        return await fallback_func(*args,**kwargs)
                    else:
                        return fallback_func(*args,**kwargs)
                
                return disable_return
            return await func(*args,**kwargs)
        return wrapper
    return decorator