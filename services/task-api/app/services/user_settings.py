from app.core.logging import get_logger
from app.db.entities import UserSettingsEntity
from app.db.unit_of_work import TaskUnitOfWork
from app.models.user_settings import UserSettingsResponse, UserSettingsUpdate

logger = get_logger(__name__)


class UserSettingsService:
    def __init__(self, uow: TaskUnitOfWork):
        self.uow = uow

    async def _get_or_create(self, user_id: int) -> UserSettingsEntity:
        """Ayar satiri yoksa varsayilanlarla olusturur (lazy init)."""
        entity = await self.uow.user_settings.get_by_user_id(user_id)
        if entity is None:
            logger.info(f"Creating default settings for user {user_id}")
            entity = await self.uow.user_settings.create(
                UserSettingsEntity(
                    user_id=user_id,
                    timezone="Europe/Istanbul",
                    reminders_enabled=True,
                    week_start=0,
                    theme="system",
                    background="kagit",
                )
            )
            await self.uow.commit()
        return entity

    async def get(self, user_id: int) -> UserSettingsResponse:
        return UserSettingsResponse.model_validate(await self._get_or_create(user_id))

    async def update(
        self, user_id: int, settings_in: UserSettingsUpdate
    ) -> UserSettingsResponse:
        entity = await self._get_or_create(user_id)
        for key, value in settings_in.model_dump(exclude_unset=True).items():
            setattr(entity, key, value)
        await self.uow.user_settings.update(entity)
        await self.uow.commit()
        return UserSettingsResponse.model_validate(entity)
