"""
Activity log yazici. Her durum degisikligi buradan gecer; istatistiklerin ve
AI'in kullanici davranisini ogrenmesinin ham verisi.
"""

import enum
from datetime import date, datetime
from typing import Any

from app.db.entities import ActivityLogEntity
from app.db.unit_of_work import TaskUnitOfWork


def _jsonable(value: Any) -> Any:
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, datetime | date):
        return value.isoformat()
    return value


def diff(entity: Any, data: dict[str, Any]) -> dict[str, list[Any]]:
    """Uygulanacak degisikliklerden gercekten degisenleri {alan: [eski, yeni]} doner."""
    changes: dict[str, list[Any]] = {}
    for key, new in data.items():
        old = getattr(entity, key, None)
        if old != new:
            changes[key] = [_jsonable(old), _jsonable(new)]
    return changes


class ActivityLogger:
    def __init__(self, uow: TaskUnitOfWork, actor: str = "user"):
        self.uow = uow
        self.actor = actor

    async def log(
        self,
        user_id: int,
        entity_type: str,
        entity_id: int,
        action: str,
        *,
        board_id: int | None = None,
        card_id: int | None = None,
        changes: dict[str, Any] | None = None,
    ) -> None:
        """Kaydi session'a ekler; commit cagiran serviste yapilir (ayni transaction)."""
        await self.uow.activity.create(
            ActivityLogEntity(
                user_id=user_id,
                entity_type=entity_type,
                entity_id=entity_id,
                action=action,
                board_id=board_id,
                card_id=card_id,
                changes={k: _jsonable(v) for k, v in changes.items()}
                if changes
                else None,
                actor=self.actor,
            )
        )
