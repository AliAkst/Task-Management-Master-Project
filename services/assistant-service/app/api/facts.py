"""Profil: asistanin kullanici hakkinda bildikleri (gor, duzelt, sil)."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user, ok
from app.db.models import UserFactEntity, get_session
from app.tools.memory_tools import CATEGORIES, PRIVATE_BY_DEFAULT, load_facts

router = APIRouter()


class FactCreate(BaseModel):
    category: str = "other"
    content: str = Field(..., min_length=1, max_length=500)
    is_private: bool | None = None  # bos: kategoriye gore varsayilan


class FactUpdate(BaseModel):
    category: str | None = None
    content: str | None = Field(None, min_length=1, max_length=500)
    is_private: bool | None = None


def _payload(f: UserFactEntity) -> dict:
    return {
        "id": f.id,
        "category": f.category,
        "content": f.content,
        "source": f.source,
        "is_private": f.is_private,
        "created_at": f.created_at,
        "updated_at": f.updated_at,
    }


def _check_category(category: str | None) -> None:
    if category is not None and category not in CATEGORIES:
        raise HTTPException(422, "Geçersiz kategori")


async def _owned(session: AsyncSession, fact_id: int, user_id: int) -> UserFactEntity:
    fact = await session.get(UserFactEntity, fact_id)
    if fact is None or fact.user_id != user_id or not fact.is_active:
        raise HTTPException(404, "Bilgi bulunamadı")
    return fact


@router.get("/facts")
async def list_facts(
    user: dict = Depends(current_user), session: AsyncSession = Depends(get_session)
):
    facts = await load_facts(session, user["id"], include_private=True)
    return ok(
        {
            "categories": [
                {"key": k, "label": v, "private_by_default": k in PRIVATE_BY_DEFAULT}
                for k, v in CATEGORIES.items()
            ],
            "facts": [_payload(f) for f in facts],
        }
    )


@router.post("/facts", status_code=201)
async def create_fact(
    data: FactCreate,
    user: dict = Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    _check_category(data.category)
    fact = UserFactEntity(
        user_id=user["id"],
        category=data.category,
        content=data.content.strip(),
        source="user_entered",
        is_private=data.is_private
        if data.is_private is not None
        else data.category in PRIVATE_BY_DEFAULT,
    )
    session.add(fact)
    await session.commit()
    return ok(_payload(fact))


@router.patch("/facts/{fact_id}")
async def update_fact(
    fact_id: int,
    data: FactUpdate,
    user: dict = Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    _check_category(data.category)
    fact = await _owned(session, fact_id, user["id"])
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(fact, key, value.strip() if isinstance(value, str) else value)
    fact.updated_at = datetime.now(UTC)
    await session.commit()
    return ok(_payload(fact))


@router.delete("/facts/{fact_id}", status_code=204)
async def delete_fact(
    fact_id: int,
    user: dict = Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    fact = await _owned(session, fact_id, user["id"])
    await session.delete(fact)
    await session.commit()
    return Response(status_code=204)
