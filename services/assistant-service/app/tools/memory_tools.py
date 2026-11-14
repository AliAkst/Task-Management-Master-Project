"""
Hafiza (Faz 5b): asistanin kullanici hakkinda ogrendikleri + hedefler.

- Bilgiler (user_facts) asistanin kendi veritabaninda; hedefler task-api'de.
- Yazma araclariyla ayni desen: prepare (dogrula + Turkce ozet) / execute,
  ayni izin kapisi (remember_fact / forget_fact / manage_goal).
- Gizlilik: saglik ve iliski bilgileri varsayilan olarak "sadece local";
  bulut model bunlari ne gorur ne degistirebilir.
"""

import re
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import UserFactEntity
from app.llm.types import Msg, ToolSpec
from app.tools.card_lookup import fold
from app.tools.fact_similarity import hours, near_duplicate, near_duplicate_text
from app.tools.task_api import TaskApiError

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
GOAL_STATUSES = ("active", "achieved", "dropped", "paused")

# "Profilimi temizle": neyin gidecegine KOD karar verir (kucuk model yanlis
# bilgiyi silebilir); model sadece belirli bilgileri ek olarak isaretleyebilir.
_DAY_SPECIFIC = re.compile(
    r"^(pazartesi|salı|çarşamba|perşembe|cuma|cumartesi|pazar|bugün|yarın)\b", re.I
)
_JUNK = re.compile(r"^kullanıcı (eklememiş|belirtmemiş|bir şey|.*görmek istiyor)", re.I)


def _norm(text: str) -> str:
    return re.sub(r"[^\w ]", "", text.casefold()).strip()


def tidy_reasons(facts: list[UserFactEntity]) -> list[tuple[UserFactEntity, str]]:
    """Temizlenecek bilgiler: tekrarlar (en eskisi kalir), tek gune ait
    ayrintilar, kullanici hakkinda olmayan anlamsiz kayitlar."""
    out: list[tuple[UserFactEntity, str]] = []
    seen: set[str] = set()
    for f in sorted(facts, key=lambda x: x.id):
        key = _norm(f.content)
        if key in seen:
            out.append((f, "tekrar"))
        elif _DAY_SPECIFIC.match(f.content.strip()):
            out.append((f, "tek güne ait"))
        elif _JUNK.match(f.content.strip()):
            out.append((f, "anlamsız"))
        seen.add(key)
    return out


# Faz 13h2: kalici silme kurali (T11) - pasif + bu kadar gunden eski
PURGE_AFTER_DAYS = 30
MERGE_MAX_PAIRS = 5  # tidy basina model cagrisi siniri
MERGE_MAX_CHARS = 200
# Gun sablonunda zaten anlatilan iskelet bilgisi (katlanmis onekler)
_TEMPLATE_HINT = re.compile(r"\b(yol|mesai|ogle|ise gid|isten don|ofis|evden calis)")
MERGE_PROMPT = (
    "Aşağıdaki iki bilgiyi TEK kısa Türkçe cümlede birleştir. Yeni bilgi ekleme, "
    "saatleri aynen koru. Sadece cümleyi yaz.\n1) {a}\n2) {b}"
)

MEMORY_ACTION_TYPES = {
    "remember_fact": "Hakkımda bilgi kaydetme / güncelleme",
    "forget_fact": "Hakkımdaki bir bilgiyi silme",
    "merge_facts": "Benzer bilgileri birleştirme",
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
        "tidy_facts",
        "Kullanıcı profilini/hafızayı temizlemeni isterse çağır: tekrar eden, tek güne ait ve "
        "anlamsız bilgiler otomatik bulunur. Yanlış olduğunu bildiğin bilgilerin id'lerini "
        "fact_ids ile ekleyebilirsin.",
        {
            "type": "object",
            "properties": {"fact_ids": {"type": "array", "items": {"type": "integer"}}},
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
    "tidy_facts": "forget_fact",
    "save_goal": "manage_goal",
}


def _clip(text: str, n: int = 80) -> str:
    return text if len(text) <= n else text[: n - 1] + "…"


async def purge_inactive(
    session: AsyncSession,
    user_id: int,
    now: datetime,
    *,
    older_than_days: int | None = PURGE_AFTER_DAYS,
) -> int:
    """Pasif kayitlari KALICI siler (yalniz bu kullanicinin). older_than_days=None:
    yas sarti yok (Profil'de kullanici istegi). Yedekten baska geri alinamaz."""
    cond = [
        UserFactEntity.user_id == user_id,
        UserFactEntity.is_active.is_(False),
    ]
    if older_than_days is not None:
        cond.append(UserFactEntity.updated_at < now - timedelta(days=older_than_days))
    res = await session.execute(delete(UserFactEntity).where(*cond))
    await session.commit()
    return int(res.rowcount or 0)


async def count_inactive(session: AsyncSession, user_id: int) -> int:
    return int(
        await session.scalar(
            select(func.count())
            .select_from(UserFactEntity)
            .where(
                UserFactEntity.user_id == user_id,
                UserFactEntity.is_active.is_(False),
            )
        )
        or 0
    )


def _near_pairs(
    facts: list[UserFactEntity],
) -> list[tuple[UserFactEntity, UserFactEntity]]:
    """Yakin tekrar ciftleri; her kayit en cok bir ciftte (kucuk id once)."""
    ordered = sorted(facts, key=lambda f: f.id)
    used: set[int] = set()
    pairs: list[tuple[UserFactEntity, UserFactEntity]] = []
    for i, a in enumerate(ordered):
        if a.id in used:
            continue
        for b in ordered[i + 1 :]:
            if b.id not in used and near_duplicate(a, b):
                pairs.append((a, b))
                used.update((a.id, b.id))
                break
    return pairs


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
        api: Any = None,
        provider: Any = None,
    ):
        self.session_maker = session_maker
        self.user_id = user_id
        self.cloud = cloud
        # Faz 13h2: sablon kurali icin task-api; birlestirme cumlesi icin YEREL model
        self.api = api
        self.provider = None if cloud else provider

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
        body, summary, _ = await self.prepare_remember_ex(content, category, fact_id)
        return body, summary

    async def prepare_remember_ex(
        self, content: str, category: str | None = None, fact_id: Any = None
    ) -> tuple[dict[str, Any], str, bool]:
        """(args, ozet, force_ask). force_ask: yakin tekrar -> izin auto olsa da onay."""
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
                    False,
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
        near = await self._near_duplicate_of(content, category)
        if near is not None:
            # Yakin tekrar: yeni kayit acma, eskisini guncelle - HER ZAMAN onayli
            args = {"fact_id": near.id, "content": content, "category": category}
            return (
                args,
                f"🧠 Bilgi güncellenir: «{_clip(near.content, 50)}» → «{_clip(content)}»",
                True,
            )
        private = category in PRIVATE_BY_DEFAULT
        args = {"content": content, "category": category, "is_private": private}
        lock = " · sadece local" if private else ""
        return (
            args,
            f"🧠 Hatırlanacak ({CATEGORIES[category]}{lock}): «{_clip(content)}»",
            False,
        )

    async def _near_duplicate_of(
        self, content: str, category: str
    ) -> UserFactEntity | None:
        async with self.session_maker() as session:
            facts = await load_facts(
                session, self.user_id, include_private=not self.cloud
            )
        for f in facts:
            if f.category == category and near_duplicate_text(f.content, content):
                return f
        return None

    async def prepare_tidy(
        self, fact_ids: list[Any] | None = None
    ) -> tuple[dict[str, Any], str]:
        async with self.session_maker() as session:
            facts = await load_facts(
                session, self.user_id, include_private=not self.cloud
            )
        picked = tidy_reasons(facts)
        chosen = {f.id for f, _ in picked}
        by_id = {f.id: f for f in facts}
        for raw in fact_ids or []:
            try:
                fid = int(raw)
            except (TypeError, ValueError):
                continue
            if fid in by_id and fid not in chosen:
                picked.append((by_id[fid], "yanlış olarak işaretlendi"))
                chosen.add(fid)

        # Faz 13h2: (2) sablonda var, (3) yakin tekrar cifti
        for f in await self._template_covered([x for x in facts if x.id not in chosen]):
            picked.append((f, "Gün şablonunda var"))
            chosen.add(f.id)
        pairs = _near_pairs([x for x in facts if x.id not in chosen])[:MERGE_MAX_PAIRS]
        merges = [
            {"ids": [a.id, b.id], "content": await self._merge_sentence(a, b)}
            for a, b in pairs
        ]

        if not picked and not merges:
            raise ValueError(
                "Temizlenecek bilgi yok: tekrar ya da tek güne ait kayıt bulunmadı"
            )
        if not merges and not any(why == "Gün şablonunda var" for _, why in picked):
            # G2: (2)/(3) yoksa eski sozlesme ve ozet aynen
            lines = [f"- «{_clip(f.content, 70)}» ({why})" for f, why in picked]
            summary = (
                f"🧹 Profil temizliği: {len(picked)} bilgi kaldırılır, "
                f"{len(facts) - len(picked)} bilgi kalır\n" + "\n".join(lines)
            )
            return {"fact_ids": sorted(chosen)}, summary
        lines = [f"− «{_clip(f.content, 70)}» ({why})" for f, why in picked]
        for (a, b), m in zip(pairs, merges, strict=True):
            lines.append(
                f"⇄ «{_clip(a.content, 50)}» + «{_clip(b.content, 50)}» → "
                f"«{_clip(m['content'], 80)}»"
            )
        summary = (
            f"🧹 Hafıza düzenleme: {len(picked)} bilgi kaldırılacak, "
            f"{len(merges)} çift birleştirilecek\n" + "\n".join(lines)
        )
        return {"forget_ids": sorted(chosen), "merges": merges}, summary

    async def _template_covered(
        self, facts: list[UserFactEntity]
    ) -> list[UserFactEntity]:
        """Gun sablonunda zaten anlatilan iskelet bilgisi (en az bir sablon varsa)."""
        cand = [
            f
            for f in facts
            if f.category in ("routine", "work")
            and len(hours(f.content)) >= 2
            and _TEMPLATE_HINT.search(fold(f.content))
        ]
        if not cand or self.api is None:
            return []
        try:
            templates = await self.api.get("/day-templates")
        except TaskApiError:
            return []
        return cand if templates else []

    async def _merge_sentence(self, a: UserFactEntity, b: UserFactEntity) -> str:
        """Yerel modelle tek cumle; bulut/hata/bos/uzun -> en yeni kaydin metni."""
        newest = max((a, b), key=lambda f: (f.updated_at.timestamp(), f.id))
        if self.provider is None or self.cloud:
            return newest.content
        if not getattr(getattr(self.provider, "info", None), "is_local", False):
            return newest.content
        prompt = MERGE_PROMPT.format(a=a.content, b=b.content)
        try:
            out = ""
            async for chunk in self.provider.stream(
                [Msg("user", prompt)], None, temperature=0, max_tokens=150
            ):
                if chunk.type == "text":
                    out += chunk.text
        except Exception:  # model hatasi tidy'yi dusurmesin
            return newest.content
        out = out.strip()
        if not out or "\n" in out or len(out) > MERGE_MAX_CHARS:
            return newest.content
        return out

    async def _execute_merge(
        self, session: AsyncSession, args: dict[str, Any], now: datetime
    ) -> dict[str, Any]:
        """Tek DB islemi: yeni birlesik kayitlar + eskiler pasif + forget'ler pasif."""
        forgotten: list[int] = []
        created: list[int] = []
        merged_pairs: list[list[int]] = []
        for fid in args.get("forget_ids", []):
            try:
                fact = await self._owned_fact(session, fid)
            except ValueError:
                continue  # arada silinmis/pasiflenmis olabilir
            fact.is_active = False
            fact.updated_at = now
            forgotten.append(fact.id)
        for m in args.get("merges", []):
            try:
                pair = [await self._owned_fact(session, i) for i in m["ids"]]
            except ValueError:
                continue  # cift bozulduysa hicbirine dokunma
            if len(pair) != 2 or pair[0].id == pair[1].id:
                continue
            content = str(m.get("content") or "").strip()[:500]
            if not content or pair[0].category != pair[1].category:
                continue
            new = UserFactEntity(
                user_id=self.user_id,
                category=pair[0].category,
                content=content,
                is_private=any(f.is_private for f in pair),
                source="ai_learned",
            )
            session.add(new)
            for f in pair:
                f.is_active = False
                f.updated_at = now
            await session.flush()
            created.append(new.id)
            merged_pairs.append([f.id for f in pair])
        await session.commit()
        return {"forgotten": forgotten, "merged": merged_pairs, "created": created}

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
            if action_type == "merge_facts":
                return await self._execute_merge(session, args, now)
            if action_type == "forget_fact" and "fact_ids" in args:
                done = []
                for fid in args["fact_ids"]:
                    try:
                        fact = await self._owned_fact(session, fid)
                    except ValueError:
                        continue  # arada silinmis olabilir
                    fact.is_active = False
                    fact.updated_at = now
                    done.append(fact.id)
                await session.commit()
                return {"forgotten": done}
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
