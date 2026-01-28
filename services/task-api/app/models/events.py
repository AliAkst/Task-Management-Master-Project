"""
Event veri modelleri.
Task event'lerinin tip ver veri yapilarini tamamlar.
"""
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

class TaskEventType(str, Enum):
    """
    Task ile ilgili event turleri.

    str'den inherit aliyoruz cunku:
    -JSON serialization'da otomatik string'e donusur
    -Routing key olarak direkt kullanilabilir olsun diye.

    Value'lar routing key formatinda:
    - "task.created" -> topic exhange'de "task.*" pattern'i yakalar.
    """
    CREATED="task.created"
    UPDATED="task.updated"
    DELETED="task.deleted"
    COMPLETED="task.completed"

@dataclass(frozen=True)
class TaskEvent:
    """
    Task event'lerinin veri yapisi.

    frozen=True cunku: Event olusturulduktan sonra degistirilemesin diye (immutable)
    Bu onemli cunku event'lar tarihsel kayit, degistirilmemeli.
    
    Attributes:
        event_type: Event'in tipi
        task_id: Etkilenen task'in ID'si
        user_id: Islemi yapan kullanici
        timestamp: Event zamani
        correlation_id: Request tracing ID
        data: Task verisi (opsiyonel olucak)
    """
    event_type: TaskEventType
    task_id: int
    user_id: int
    timestamp: datetime
    correlation_id: str | None = None
    data: dict[str, Any] |None = None

    def to_dict(self) -> dict[str, Any]:
        """
        Event'i JSON-serializable dict'e cevirir.

        Returns:
            dict: Serialize edilmis event
        """
        return{
            "event_type": self.event_type.value,
            "task_id":self.task_id,
            "user_id":self.user_id,
            "timestamp":self.timestamp.isoformat(),
            "correlation_id":self.correlation_id,
            "data":self.data,
        }