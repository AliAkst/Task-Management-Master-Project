"""AI islemleri: onay / ret, bekleyenler, izin ayarlari."""

from datetime import UTC, datetime
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import app.api.chat as chat_module
from app.agent.actions import (
    action_payload,
    load_modes,
    record_outcome_in_history,
    set_mode,
)
from app.api.deps import current_user, ok
from app.db.models import AiActionEntity, get_session
from app.tools.memory_tools import MemoryTools
from app.tools.privacy import PrivacyFilter
from app.tools.task_api import TaskApiError
from app.tools.write_tools import ACTION_TYPES, WriteTools

router = APIRouter()
Mode = Literal["ask", "auto", "never"]


class ApproveRequest(BaseModel):
    # "Bu tur islemleri bundan sonra otomatik yap"
    remember_auto: bool = False


class RejectRequest(BaseModel):
    reason: str | None = Field(None, max_length=2000)


class PermissionUpdate(BaseModel):
    mode: Mode


async def _owned_action(
    session: AsyncSession, action_id: int, user_id: int
) -> AiActionEntity:
    action = await session.get(AiActionEntity, action_id)
    if action is None or action.user_id != user_id:
        raise HTTPException(404, "İşlem bulunamadı")
    return action


def _must_be_pending(action: AiActionEntity) -> None:
    if action.status != "proposed":
        raise HTTPException(409, f"Bu işlem zaten sonuçlandı ({action.status})")


@router.get("/actions")
async def list_actions(
    status: str | None = None,
    conversation_id: int | None = None,
    user: dict = Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    query = select(AiActionEntity).where(AiActionEntity.user_id == user["id"])
    if status:
        query = query.where(AiActionEntity.status == status)
    if conversation_id is not None:
        query = query.where(AiActionEntity.conversation_id == conversation_id)
    rows = await session.scalars(query.order_by(AiActionEntity.id.desc()).limit(100))
    return ok([action_payload(a) for a in rows])


@router.post("/actions/{action_id}/approve")
async def approve(
    action_id: int,
    data: ApproveRequest,
    user: dict = Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    action = await _owned_action(session, action_id, user["id"])
    _must_be_pending(action)
    api = chat_module.TaskApiClient(user["token"])
    try:
        settings = await api.get("/settings/")
        tz = ZoneInfo(settings.get("timezone") or chat_module.DEFAULT_TZ)
        # Gizlilik kontrolu oneri aninda yapildi; argumanlar zaten cozuldu
        memory = MemoryTools(chat_module.session_maker, user["id"], cloud=False)
        writer = WriteTools(api, PrivacyFilter(active=False), tz, memory=memory)
        try:
            action.result = await writer.execute(action.action_type, action.args)
            action.status = "executed"
        except TaskApiError as e:
            action.result = {"error": e.message}
            action.status = "failed"
    finally:
        await api.close()
    action.decided_at = datetime.now(UTC)
    if data.remember_auto and action.status == "executed":
        await set_mode(session, user["id"], action.action_type, "auto")
    await record_outcome_in_history(session, action)
    await session.commit()
    return ok(action_payload(action))


@router.post("/actions/{action_id}/reject")
async def reject(
    action_id: int,
    data: RejectRequest,
    user: dict = Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    action = await _owned_action(session, action_id, user["id"])
    _must_be_pending(action)
    action.status = "rejected"
    action.user_feedback = (data.reason or "").strip() or None
    action.decided_at = datetime.now(UTC)
    await record_outcome_in_history(session, action)
    await session.commit()
    return ok(action_payload(action))


@router.get("/permissions")
async def permissions(
    user: dict = Depends(current_user), session: AsyncSession = Depends(get_session)
):
    modes = await load_modes(session, user["id"])
    return ok(
        [
            {"action_type": t, "label": label, "mode": modes[t]}
            for t, label in ACTION_TYPES.items()
        ]
    )


@router.put("/permissions/{action_type}")
async def update_permission(
    action_type: str,
    data: PermissionUpdate,
    user: dict = Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    if action_type not in ACTION_TYPES:
        raise HTTPException(404, "Bilinmeyen işlem türü")
    await set_mode(session, user["id"], action_type, data.mode)
    await session.commit()
    return ok({"action_type": action_type, "mode": data.mode})
