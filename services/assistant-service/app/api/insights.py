"""Asistanin gozlemleri (Faz 6b): liste, haftalik analizi baslat, onayla / reddet."""

from datetime import UTC, date, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user, ok
from app.api.jobs import WEEKLY, job_out, latest_job, start_job
from app.db.models import AiInsightEntity, UserFactEntity, get_session
from app.tools.memory_tools import PRIVATE_BY_DEFAULT

router = APIRouter()


class RejectInsight(BaseModel):
    reason: str | None = Field(None, max_length=2000)


class ConfirmInsight(BaseModel):
    # Kullanici cumleyi bilgi olarak kaydetmeden once duzeltebilir
    content: str | None = Field(None, min_length=1, max_length=1000)


def insight_payload(i: AiInsightEntity) -> dict[str, Any]:
    return {
        "id": i.id,
        "category": i.category,
        "observation": i.observation,
        "evidence": i.evidence,
        "status": i.status,
        "user_feedback": i.user_feedback,
        "fact_id": i.fact_id,
        "created_at": i.created_at,
        "decided_at": i.decided_at,
    }


async def _owned(
    session: AsyncSession, insight_id: int, user_id: int
) -> AiInsightEntity:
    row = await session.get(AiInsightEntity, insight_id)
    if row is None or row.user_id != user_id:
        raise HTTPException(404, "Gözlem bulunamadı")
    if row.status != "new":
        raise HTTPException(409, f"Bu gözlem zaten sonuçlandı ({row.status})")
    return row


@router.get("/insights")
async def list_insights(
    user: dict = Depends(current_user), session: AsyncSession = Depends(get_session)
):
    """Bekleyen gozlemler + son kararlar + son haftalik analiz isi."""
    rows = list(
        await session.scalars(
            select(AiInsightEntity)
            .where(AiInsightEntity.user_id == user["id"])
            .order_by(AiInsightEntity.id.desc())
            .limit(50)
        )
    )
    return ok(
        {
            "job": await job_out(
                session, await latest_job(session, user["id"], WEEKLY)
            ),
            "items": [insight_payload(r) for r in rows],
        }
    )


@router.post("/insights/analyze")
async def analyze(day: date | None = None, user: dict = Depends(current_user)):
    """Haftalik analizi simdi baslatir (son 4 hafta, `day` dahil)."""
    return ok(await start_job(user, WEEKLY, day or date.today()))


@router.post("/insights/{insight_id}/confirm")
async def confirm(
    insight_id: int,
    data: ConfirmInsight,
    user: dict = Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    """Gozlem dogru: kalici bilgi olur (sohbette asistan dikkate alir)."""
    row = await _owned(session, insight_id, user["id"])
    fact = UserFactEntity(
        user_id=user["id"],
        category=row.category,
        content=(data.content or row.observation).strip(),
        source="insight_confirmed",
        is_private=row.category in PRIVATE_BY_DEFAULT,
    )
    session.add(fact)
    await session.flush()
    row.status = "confirmed"
    row.fact_id = fact.id
    row.decided_at = datetime.now(UTC)
    await session.commit()
    return ok(insight_payload(row))


@router.post("/insights/{insight_id}/reject")
async def reject(
    insight_id: int,
    data: RejectInsight,
    user: dict = Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    """Gozlem yanlis ya da gereksiz: 4 hafta boyunca tekrar onerilmez."""
    row = await _owned(session, insight_id, user["id"])
    row.status = "rejected"
    row.user_feedback = (data.reason or "").strip() or None
    row.decided_at = datetime.now(UTC)
    await session.commit()
    return ok(insight_payload(row))
