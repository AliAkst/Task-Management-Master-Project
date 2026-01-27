"""
Advanced Healt Check Sistemi.
Bu modul uygulamanin ve bagimliliklarin durumunu kontrol eder.
Kubernetes liveness/readiness probe;lari icin kullanilir.
"""
import asyncio
import time
import shutil
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any
from sqlalchemy import text
from app.config import settings
from app.core.logging import get_logger
from app.db.database import async_session_maker
from app.core.cache import redis_cache

logger = get_logger(__name__)

class HealthStatus(Enum):
    """
    Saglik durumu seviyeleri.

    Attributes:
        HEALTHY: bilesen tamamen saglikli
        DEGRADED: Calisiyor ama performansi dusuk
        UNHEALTHY: Bilesen calismiyor.
    """
    HEALTHY="healthy"
    DEGRADED= "degraded"
    UNHEALTHY="unhealthy"

@dataclass
class HealthCheckResult:
    """
    Tek bir health check sonucunu icerir.

    Attributes:
        name: Check adi (orn: "database", "redis")
        status: saglik durumu
        latency_ms: kontrol suresi(ms)
        message: Opsiyonel aciklama veya hata mesaji
        details: Ek detaylar (orn versiyon, baglanti sayisi)
        timestamp: Kontrol zamani
    """
    name:str
    status: HealthStatus
    latency_ms: float = 0.0
    message: str | None = None
    details: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self)-> dict:
        """JSON serilizable dict dondurur."""
        return{
            "name":self.name,
            "status": self.status.value,
            "latency_ms":round(self.latency_ms, 2),
            "message":self.message,
            "details":self.details,
            "timestamp":self.timestamp.isoformat(),
        }

class BaseHealthCheck(ABC):
    """
    Health check'ler icin abstract base class.
    
    Tum health check'ler bu class'dan turer.
    
    Args:
        name: Check adi
        timeout: Maksimum kontrol suresi 
        critical: True ise bu check basarisiz olunca readiness da basarisiz
    """
    def __init__(
        self,
        name:str,
        timeout:float= 5.0,
        critical: bool = True
    ):
        self.name=name
        self.timeout=timeout
        self.critical=critical
    
    @abstractmethod
    async def check(self) -> HealthCheckResult:
        """
        Saglik kontrolunu gerceklestirir.

        Returns: 
            HealthCheckResult: Kontrol sonucu

        Raises:
            Herhangi bir exception firlatilmaz, hata durumunda
            UNHEALTHY status dondurulur.
        """
        pass

    async def execute(self)->HealthCheckResult:
        """
        Timeout ile sarilmis health check calistirir.

        Returns: 
            HealthCheckResult: Kontrol sonucu)(timeout olursa UNHEALTHY)
        """
        start =time.perf_counter()

        try:
            result=await asyncio.wait_for(
                self.check(),
                timeout=self.timeout
            )
            result.latency_ms = (time.perf_counter()-start) * 1000
            return result        
        
        except asyncio.TimeoutError:
            latency= (time.perf_counter()- start) * 1000
            logger.warning(f"Health check '{self.name}' timeout ({self.timeout})")
            return HealthCheckResult(
                name=self.name,
                status=HealthStatus.UNHEALTHY,
                latency_ms=latency,
                message=f"Timeout after {self.timeout}"
            )
        except Exception as e:
            latency = (time.perf_counter()- start) * 1000
            logger.error(f"Health check '{self.name}' failed {e}")
            return HealthCheckResult(
                name=self.name,
                status=HealthStatus.UNHEALTHY,
                latency_ms=latency,
                message=str(e)
            )
class DatabaseHealthCheck(BaseHealthCheck):
    """
    Database baglanti kontrolu.
    
    Args:
        name: Check adi
        timeout: Maksimum kontrol suresi
        critical: Kritik mi (readiness'i etkiler.)
    """
    def __init__(
        self,
        name: str = "database",
        timeout: float = 5.0,
        critical: bool = True
    ):
        super().__init__(name,timeout,critical)

    async def check(self) -> HealthCheckResult:
        """
        Database'e basit bir sorgu atar.

        Returns:
            HealthCheckResult: Baglanti durumu
        """
        try:
            async with async_session_maker() as session:
                await session.execute(text("SELECT 1"))

            return HealthCheckResult(
                name=self.name,
                status=HealthStatus.HEALTHY,
                message="Database connection OK",
                details={"type":"postgresql"}
            )
        except Exception as e:
            return HealthCheckResult(
                name=self.name,
                status=HealthStatus.UNHEALTHY,
                message=str(e)
            )
class RedisHealthCheck(BaseHealthCheck):
    """
    Redis baglanti kontrolu.

    Args:
        name: Check adi
        timeout: Maksimum kontrol suresi
        critical: Kritik mi (False = cache olmadan da calisabiliriz)
    """
    def __init__(
        self,
        name:str = "redis",
        timeout:float=2.0,
        critical: bool = False
    ):
        super().__init__(name,timeout,critical)
    
    async def check(self) -> HealthCheckResult:
        """
        Redise Ping atar
        Returns:
            HealthCheckResult: Baglanti durumu
        """
        try:
            if redis_cache.redis is None:
                return HealthCheckResult(
                    name=self.name,
                    status=HealthStatus.UNHEALTHY,
                    message="Redis Not Connected",
                )
            else:
                await redis_cache.redis.ping()

                return HealthCheckResult(
                    name=self.name,
                    status=HealthStatus.HEALTHY,
                    message="Redis connection OK",
                    details={"host": settings.redis_host, "port": settings.redis_port}
            )
        except Exception as e:
            return HealthCheckResult(
                name=self.name,
                status=HealthStatus.UNHEALTHY,
                message=str(e)
            )

class DiskHealthCheck(BaseHealthCheck):
    """
    Disk Alani kontrolu.

    Args:
        name: check adi
        timeout: Maksimum kontrol suresi
        critical: Kritik mi 
        min_free_gb: Minimum Bos alan (GB)
    """
    def __init__(
        self,
        name:str="disk",
        timeout:float=1.0,
        critical: bool= False,
        min_free_gb: float = 1.0
    ):
        super().__init__(name, timeout, critical)
        self.min_free_gb=min_free_gb
    
    async def check(self) -> HealthCheckResult:
        """
        Disk alanini kontrol eder.
        Returns:
            HealthCheckResult: Disk durumu
        """
        try:
            total, used, free= shutil.disk_usage("/")
            free_gb= free / (1024 ** 3)

            if free_gb < self.min_free_gb:
                return HealthCheckResult(
                    name=self.name,
                    status=HealthStatus.DEGRADED,
                    message=f"Low Disk space: {free_gb:.1f} GB free",
                    details={"free_gb": round(free_gb, 2),"min_required_gb": self.min_free_gb}
                )
            
            return HealthCheckResult(
                name=self.name,
                status=HealthStatus.HEALTHY,
                message="Disk Space OK",
                details={"free_gb": round(free_gb, 2)}
            )
        except Exception as e:
            return HealthCheckResult(
                name=self.name,
                status=HealthStatus.UNHEALTHY,
                message=str(e)
            )

class HealthChecker:
    """
    Tum health check'leri yoneten ana class.

    Args:
        checks: Baslangicta eklenecek check listesi
    """

    def __init__(self, checks: list[BaseHealthCheck]|None = None):
        self._checks: list[BaseHealthCheck]= checks or []
    
    def add_check(self,check: BaseHealthCheck) -> None:
        """
        Yeni bir health check ekler.

        Args:
            check: Eklenecek health check
        """
        self._checks.append(check)
        logger.debug(f"Health check eklendi:{check.name}")
    
    async def check_all(self) -> dict:
        """
        Tum checkleri paralel calistirir.
        
        Returns:
            dict: Tum sonuclari iceren rapor
        """
        if not self._checks:
            return{
                "status":HealthStatus.HEALTHY.value,
                "checks":{},
                "timestamp":datetime.utcnow().isoformat()
            }
        
        else:
            # Tum checkleri paralel calistirir.
            results=await asyncio.gather(
                *[check.execute() for check in self._checks],
                return_exceptions= True
            )
            # Sonuclari isle
            checks_dict = {}
            overall_status = HealthStatus.HEALTHY

            for i, result in enumerate(results):
                check= self._checks[i]

                if isinstance(result, Exception):
                    result = HealthCheckResult(
                        name=check.name,
                        status=HealthStatus.UNHEALTHY,
                        message=str(result)
                    )
                checks_dict[result.name] = result.to_dict()

                if result.status == HealthStatus.UNHEALTHY:
                    if check.critical:
                        overall_status = HealthStatus.UNHEALTHY
                    elif overall_status != HealthStatus.UNHEALTHY:
                        overall_status= HealthStatus.DEGRADED
                elif result.status == HealthStatus.DEGRADED:
                    if overall_status == HealthStatus.HEALTHY:
                        overall_status = HealthStatus.DEGRADED
            return {
                "status":overall_status.value,
                "checks": checks_dict,
                "timestamp":datetime.utcnow().isoformat()
            }
    async def is_live(self)-> bool:
        """
        Liveness check - uygulama calisiyor mu ?

        Returns:
            bool: True ise uygulama ayaktadir.
        
        """
        return True
    async def is_ready(self) -> bool:
        """
        Readiness check - Trafik alabilir mi ?

        Returns:
            bool: True ise trafik alabilir.
        """
        result = await self.check_all()
        return result["status"] != HealthStatus.UNHEALTHY.value

# ----- GLOBAL HEALTH CHECKER -----
health_checker = HealthChecker()
health_checker.add_check(DatabaseHealthCheck())
health_checker.add_check(RedisHealthCheck())
health_checker.add_check(DiskHealthCheck())