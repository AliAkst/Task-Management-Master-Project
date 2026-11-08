from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.resilience import with_db_retry
from app.db.entities.integration import (
    ExternalLinkEntity,
    IntegrationAccountEntity,
    OAuthClientEntity,
)

from .base import BaseRepository


class IntegrationAccountRepository(BaseRepository[IntegrationAccountEntity]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, IntegrationAccountEntity)

    @with_db_retry
    async def list_for_user(self, user_id: int) -> list[IntegrationAccountEntity]:
        result = await self.session.execute(
            select(IntegrationAccountEntity)
            .where(IntegrationAccountEntity.user_id == user_id)
            .order_by(IntegrationAccountEntity.id)
        )
        return list(result.scalars().all())

    @with_db_retry
    async def get_for_provider(
        self, user_id: int, provider: str
    ) -> IntegrationAccountEntity | None:
        result = await self.session.execute(
            select(IntegrationAccountEntity).where(
                IntegrationAccountEntity.user_id == user_id,
                IntegrationAccountEntity.provider == provider,
            )
        )
        return result.scalar_one_or_none()

    @with_db_retry
    async def list_by_provider(self, provider: str) -> list[IntegrationAccountEntity]:
        """Tum kullanicilarin aktif hesaplari (zamanlayici icin)."""
        result = await self.session.execute(
            select(IntegrationAccountEntity).where(
                IntegrationAccountEntity.provider == provider,
                IntegrationAccountEntity.status == "active",
            )
        )
        return list(result.scalars().all())


class ExternalLinkRepository(BaseRepository[ExternalLinkEntity]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, ExternalLinkEntity)

    @with_db_retry
    async def get_by_external(
        self, user_id: int, provider: str, entity_type: str, external_id: str
    ) -> ExternalLinkEntity | None:
        result = await self.session.execute(
            select(ExternalLinkEntity).where(
                ExternalLinkEntity.user_id == user_id,
                ExternalLinkEntity.provider == provider,
                ExternalLinkEntity.entity_type == entity_type,
                ExternalLinkEntity.external_id == external_id,
            )
        )
        return result.scalar_one_or_none()

    @with_db_retry
    async def external_ids(
        self, user_id: int, provider: str, entity_type: str
    ) -> set[str]:
        result = await self.session.execute(
            select(ExternalLinkEntity.external_id).where(
                ExternalLinkEntity.user_id == user_id,
                ExternalLinkEntity.provider == provider,
                ExternalLinkEntity.entity_type == entity_type,
            )
        )
        return set(result.scalars().all())

    @with_db_retry
    async def for_entity(
        self, entity_type: str, entity_id: int
    ) -> list[ExternalLinkEntity]:
        result = await self.session.execute(
            select(ExternalLinkEntity).where(
                ExternalLinkEntity.entity_type == entity_type,
                ExternalLinkEntity.entity_id == entity_id,
            )
        )
        return list(result.scalars().all())

    @with_db_retry
    async def for_entities(
        self, provider: str | None, entity_type: str, entity_ids: list[int]
    ) -> dict[int, ExternalLinkEntity]:
        """Verilen yerel kayitlarin baglantilari (entity_id -> baglanti)."""
        if not entity_ids:
            return {}
        query = select(ExternalLinkEntity).where(
            ExternalLinkEntity.entity_type == entity_type,
            ExternalLinkEntity.entity_id.in_(entity_ids),
        )
        if provider is not None:
            query = query.where(ExternalLinkEntity.provider == provider)
        result = await self.session.execute(query)
        return {link.entity_id: link for link in result.scalars().all()}

    @with_db_retry
    async def for_parent(
        self, user_id: int, provider: str, entity_type: str, parent_external_id: str
    ) -> list[ExternalLinkEntity]:
        """Bir ust nesnenin (ornegin takvim) altindaki baglantilar."""
        result = await self.session.execute(
            select(ExternalLinkEntity).where(
                ExternalLinkEntity.user_id == user_id,
                ExternalLinkEntity.provider == provider,
                ExternalLinkEntity.entity_type == entity_type,
                ExternalLinkEntity.external_parent_id == parent_external_id,
            )
        )
        return list(result.scalars().all())

    @with_db_retry
    async def list_for_provider(
        self, user_id: int, provider: str, entity_type: str
    ) -> list[ExternalLinkEntity]:
        result = await self.session.execute(
            select(ExternalLinkEntity).where(
                ExternalLinkEntity.user_id == user_id,
                ExternalLinkEntity.provider == provider,
                ExternalLinkEntity.entity_type == entity_type,
            )
        )
        return list(result.scalars().all())

    @with_db_retry
    async def list_pending_push(
        self, user_id: int, provider: str
    ) -> list[ExternalLinkEntity]:
        """Yerelde degisip dis sisteme henuz yazilmamis baglantilar (outbox)."""
        result = await self.session.execute(
            select(ExternalLinkEntity)
            .where(
                ExternalLinkEntity.user_id == user_id,
                ExternalLinkEntity.provider == provider,
                ExternalLinkEntity.pending_push.is_(True),
            )
            .order_by(ExternalLinkEntity.id)
        )
        return list(result.scalars().all())

    async def delete_children(
        self, user_id: int, provider: str, parent_external_id: str
    ) -> None:
        """Bir ust nesnenin (ornegin Trello board) alt baglantilarini siler."""
        await self.session.execute(
            delete(ExternalLinkEntity).where(
                ExternalLinkEntity.user_id == user_id,
                ExternalLinkEntity.provider == provider,
                ExternalLinkEntity.external_parent_id == parent_external_id,
            )
        )

    async def delete_for_provider(self, user_id: int, provider: str) -> None:
        """Hesap kaldirilinca baglantilar silinir; yerel kayitlar kalir."""
        await self.session.execute(
            delete(ExternalLinkEntity).where(
                ExternalLinkEntity.user_id == user_id,
                ExternalLinkEntity.provider == provider,
            )
        )


class OAuthClientRepository(BaseRepository[OAuthClientEntity]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, OAuthClientEntity)

    @with_db_retry
    async def get_for_provider(
        self, user_id: int, provider: str
    ) -> OAuthClientEntity | None:
        result = await self.session.execute(
            select(OAuthClientEntity).where(
                OAuthClientEntity.user_id == user_id,
                OAuthClientEntity.provider == provider,
            )
        )
        return result.scalar_one_or_none()
