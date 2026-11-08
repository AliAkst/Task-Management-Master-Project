"""
Hafiza (Faz 5b): asistanin kullanici hakkinda ogrendikleri + hedefler.

- Bilgiler (user_facts) asistanin kendi veritabaninda; hedefler task-api'de.
- Yazma araclariyla ayni desen: prepare (dogrula + Turkce ozet) / execute,
  ayni izin kapisi (remember_fact / forget_fact / manage_goal).
- Gizlilik: saglik ve iliski bilgileri varsayilan olarak "sadece local";
  bulut model bunlari ne gorur ne degistirebilir.
"""

from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import UserFactEntity
from app.llm.types import ToolSpec

# Kategori -> kullaniciya gorunen ad
CATEGORIES: dict[str, str] = {
    "personal": "Kişisel bilgiler",
    "routine": "Rutinler ve çalışma düzeni",
    "preference": "Tercihler",
    "work": "İş ve kariyer",
    "health": "Sağlık ve spor",
    "relationship": "İlişkiler",
    "other": "Diğer",
}
PRIVATE_BY_DEFAULT = {"health", "relationship"}
GOAL_STATUSES = ("active", "achieved", "dropped")

MEMORY_ACTION_TYPES = {
    "remember_fact": "Hakkımda bilgi kaydetme / güncelleme",
    "forget_fact": "Hakkımdaki bir bilgiyi silme",
    "manage_goal": "Hedef ekleme / güncelleme",
}

MEMORY_SPECS: list[ToolSpec] = [
    ToolSpec(
        "remember_fact",
        "Kullanıcı hakkında kalıcı bir bilgi kaydeder ya da (fact_id ile) günceller. "
        "Sadece kullanıcının açıkça söylediği, ileride işe yarayacak şeyleri kaydet; tahmin yürütme. "
        "Kategoriler: " + ", ".join(CATEGORIES) + ".",
        {
            "type": "object",
            "properties": {
                "category": {"type": "string", "enum": list(CATEGORIES)},
                "content": {
                    "type": "string",
                    "description": "Tek cümle, kullanıcı hakkında (örn. 'Haftada 3 gün sabah koşuyor')",
                },
                "fact_id": {
                    "type": "integer",
                    "description": "Güncellenecek bilginin id'si",
                },
            },
            "required": ["content"],
        },
    ),
    ToolSpec(
        "forget_fact",
        "Kullanıcı hakkında artık doğru olmayan bir bilgiyi siler.",
        {
            "type": "object",
            "properties": {"fact_id": {"type": "integer"}},
            "required": ["fact_id"],
        },
    ),
    ToolSpec(
        "save_goal",
        "Kullanıcının hayat hedefini ekler ya da (goal_id ile) günceller: başlık, neden, hedef tarih, ilgili board, durum.",
        {
            "type": "object",
            "properties": {
                "goal_id": {"type": "integer"},
                "title": {"type": "string"},
                "why": {"type": "string"},
                "target_date": {"type": "string", "description": "YYYY-MM-DD"},
                "board_id": {"type": "integer"},
                "status": {"type": "string", "enum": list(GOAL_STATUSES)},
            },
        },
    ),
]
MEMORY_TOOL_NAMES = {s.name for s in MEMORY_SPECS}
TOOL_TO_ACTION = {
    "remember_fact": "remember_fact",
    "forget_fact": "forget_fact",
    "save_goal": "manage_goal",
}


def _clip(text: str, n: int = 80) -> str:
    return text if len(text) <= n else text[: n - 1] + "…"


async def load_facts(
    session: AsyncSession, user_id: int, *, include_private: bool
) -> list[UserFactEntity]:
    query = select(UserFactEntity).where(
        UserFactEntity.user_id == user_id, UserFactEntity.is_active.is_(True)
    )
    if not include_private:
        query = query.where(UserFactEntity.is_private.is_(False))
    return list(
        await session.scalars(
            query.order_by(UserFactEntity.category, UserFactEntity.id)
        )
    )


class MemoryTools:
    """Bilgi islemleri (asistan DB'si). Hedef islemleri WriteTools uzerinden task-api'ye."""

    def __init__(
        self,
        session_maker: async_sessionmaker[AsyncSession],
        user_id: int,
        *,
        cloud: bool,
    ):
        self.session_maker = session_maker
        self.user_id = user_id
        self.cloud = cloud

    async def _owned_fact(self, session: AsyncSession, fact_id: Any) -> UserFactEntity:
        try:
            fid = int(fact_id)
        except (TypeError, ValueError) as e:
            raise ValueError("fact_id tam sayı olmalı") from e
        fact = await session.get(UserFactEntity, fid)
        if fact is None or fact.user_id != self.user_id or not fact.is_active:
            raise ValueError(f"{fid} numaralı bilgi bulunamadı")
        if self.cloud and fact.is_private:
            raise ValueError(
                "Bu bilgi gizli (sadece local model); bulut model değiştiremez."
            )
        return fact

    # ---------------- hazirlik ----------------
    async def prepare_remember(
        self, content: str, category: str | None = None, fact_id: Any = None
    ) -> tuple[dict[str, Any], str]:
        content = str(content or "").strip()
        if not content:
            raise ValueError("content boş olamaz")
        if len(content) > 500:
            raise ValueError("Bilgi tek, kısa bir cümle olmalı (en fazla 500 karakter)")
        if category is not None and category not in CATEGORIES:
            raise ValueError("category şunlardan biri olmalı: " + ", ".join(CATEGORIES))
        if fact_id is not None:
            async with self.session_maker() as session:
                fact = await self._owned_fact(session, fact_id)
                args = {
                    "fact_id": fact.id,
                    "content": content,
                    "category": category or fact.category,
                }
                return (
                    args,
                    f"🧠 Bilgi güncellenir: «{_clip(fact.content, 50)}» → «{_clip(content)}»",
                )
        async with self.session_maker() as session:
            same = await session.scalar(
                select(UserFactEntity).where(
                    UserFactEntity.user_id == self.user_id,
                    UserFactEntity.is_active.is_(True),
                    func.lower(UserFactEntity.content) == content.lower(),
                )
            )
        if same is not None:
            raise ValueError(f"Bu bilgi zaten kayıtlı ({same.id}); tekrar kaydetme")
        category = category or "other"
        private = category in PRIVATE_BY_DEFAULT
        args = {"content": content, "category": category, "is_private": private}
        lock = " · sadece local" if private else ""
        return (
            args,
            f"🧠 Hatırlanacak ({CATEGORIES[category]}{lock}): «{_clip(content)}»",
        )

    async def prepare_forget(self, fact_id: Any) -> tuple[dict[str, Any], str]:
        async with self.session_maker() as session:
            fact = await self._owned_fact(session, fact_id)
            return {"fact_id": fact.id}, f"🗑 Unutulacak: «{_clip(fact.content)}»"

    # ---------------- calistirma ----------------
    async def execute(self, action_type: str, args: dict[str, Any]) -> dict[str, Any]:
        async with self.session_maker() as session:
            now = datetime.now(UTC)
            if action_type == "remember_fact":
                if "fact_id" in args:
                    fact = await self._owned_fact(session, args["fact_id"])
                    fact.content = args["content"]
                    fact.category = args["category"]
                    fact.updated_at = now
                else:
                    fact = UserFactEntity(
                        user_id=self.user_id,
                        category=args["category"],
                        content=args["content"],
                        is_private=args.get("is_private", False),
                        source="ai_learned",
                    )
                    session.add(fact)
                await session.commit()
                return {"fact_id": fact.id}
            if action_type == "forget_fact":
                fact = await self._owned_fact(session, args["fact_id"])
                fact.is_active = False
                fact.updated_at = now
                await session.commit()
                return {"forgotten": fact.id}
        raise ValueError(f"Bilinmeyen hafıza işlemi: {action_type}")


def validate_goal_args(args: dict[str, Any]) -> dict[str, Any]:
    """save_goal argumanlarini task-api govdesine cevirir (hedef create/update)."""
    body: dict[str, Any] = {}
    if args.get("title") is not None:
        title = str(args["title"]).strip()
        if not title:
            raise ValueError("title boş olamaz")
        body["title"] = title[:200]
    if args.get("why") is not None:
        body["why"] = str(args["why"])
    if args.get("target_date"):
        try:
            body["target_date"] = date.fromisoformat(
                str(args["target_date"])[:10]
            ).isoformat()
        except ValueError as e:
            raise ValueError("target_date YYYY-MM-DD olmalı") from e
    if args.get("board_id") is not None:
        body["board_id"] = int(args["board_id"])
    if args.get("status") is not None:
        if args["status"] not in GOAL_STATUSES:
            raise ValueError(
                "status şunlardan biri olmalı: " + ", ".join(GOAL_STATUSES)
            )
        body["status"] = args["status"]
    if args.get("goal_id") is None and "title" not in body:
        raise ValueError("Yeni hedef için title gerekli")
    if args.get("goal_id") is not None and not body:
        raise ValueError("Değişecek bir alan verilmedi")
    return body
