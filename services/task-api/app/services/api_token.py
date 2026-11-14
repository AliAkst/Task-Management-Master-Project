"""Kisisel erisim jetonu (PAT) servisi (Faz 13b)."""

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta

from app.core.exceptions import ApiTokenNotFoundException, TooManyTokensException
from app.db.entities.api_token import ApiTokenEntity
from app.db.unit_of_work import TaskUnitOfWork
from app.models.api_token import ApiTokenCreate

PAT_PREFIX = "pat_"
MAX_ACTIVE_TOKENS = 10
LAST_USED_INTERVAL = timedelta(seconds=60)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class ApiTokenService:
    def __init__(self, uow: TaskUnitOfWork):
        self.uow = uow

    async def create(
        self, user_id: int, data: ApiTokenCreate
    ) -> tuple[ApiTokenEntity, str]:
        if await self.uow.api_tokens.count_active(user_id) >= MAX_ACTIVE_TOKENS:
            raise TooManyTokensException()
        scopes = ["read", "write"] if "write" in data.scopes else ["read"]
        token = PAT_PREFIX + secrets.token_urlsafe(32)
        now = datetime.now(UTC)
        entity = ApiTokenEntity(
            user_id=user_id,
            name=data.name,
            token_hash=hash_token(token),
            token_hint=token[: len(PAT_PREFIX) + 6] + "…",
            scopes=scopes,
            created_at=now,
            expires_at=(
                now + timedelta(days=data.expires_in_days)
                if data.expires_in_days
                else None
            ),
        )
        await self.uow.api_tokens.create(entity)
        await self.uow.commit()
        return entity, token

    async def list(self, user_id: int) -> list[ApiTokenEntity]:
        return await self.uow.api_tokens.list_active(user_id)

    async def revoke(self, user_id: int, token_id: int) -> None:
        entity = await self.uow.api_tokens.get_by_id(token_id)
        if not entity or entity.user_id != user_id or entity.revoked_at is not None:
            raise ApiTokenNotFoundException()
        entity.revoked_at = datetime.now(UTC)
        await self.uow.commit()

    async def authenticate(self, token: str) -> ApiTokenEntity | None:
        """Gecerli (iptal/sure dolumu yok) jetonu doner; yoksa None."""
        digest = hash_token(token)
        entity = await self.uow.api_tokens.get_by_hash(digest)
        if entity is None or not hmac.compare_digest(entity.token_hash, digest):
            return None
        if entity.revoked_at is not None:
            return None
        if entity.expires_at is not None and entity.expires_at <= datetime.now(UTC):
            return None
        return entity

    async def touch(self, entity: ApiTokenEntity) -> None:
        now = datetime.now(UTC)
        if (
            entity.last_used_at is None
            or now - entity.last_used_at >= LAST_USED_INTERVAL
        ):
            entity.last_used_at = now
            await self.uow.commit()
