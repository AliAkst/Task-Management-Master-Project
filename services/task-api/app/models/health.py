"""
Health check veri modelleri.
Health check sonuclarini ve durum bilgilerini tanimlar.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

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