"""Ingilizce kocu (Faz 13j1): profil, kelime (SM-2), hata gunlugu, seanslar, bugun, ilerleme.

Saat `_now()` uzerinden okunur (testler sabitler); "bugun" kullanicinin saat dilimine gore.
"""

from collections import Counter
from datetime import UTC, date, datetime, timedelta

from app.core.exceptions import AppException, ConflictException, NotFoundException
from app.db.entities import (
    EnglishMistakeEntity,
    EnglishProfileEntity,
    EnglishSessionEntity,
    EnglishVocabEntity,
)
from app.db.unit_of_work import TaskUnitOfWork
from app.models.english import (
    CategoryCount,
    MistakeItem,
    ProfileInput,
    ProfileResponse,
    ProgressResponse,
    SessionCreate,
    TodayResponse,
    VocabItem,
    VocabResponse,
    VocabStats,
    VocabUpdate,
    WeekCategoryCount,
    WeekMinutes,
)
from app.services.srs import SrsCard, new_card, review
from app.services.timeutil import day_bounds, local_today, user_tz

DUE_IN_TODAY = 15
TASK_TEXTS = {
    "speaking": "5 dk sesli konuş: bugünün planını İngilizce anlat.",
    "writing": "3–5 cümle yaz: dün ne yaptın?",
    "vocab": "Vadesi gelen kelimeleri tekrar et, 2 örnek cümle kur.",
    "grammar": "En sık hata kategorinden 5 düzeltme alıştırması.",
}
ACTOR_SOURCE = {"ai": "local", "mcp": "claude"}


def _now() -> datetime:
    return datetime.now(UTC)


def term_key(term: str) -> str:
    """Katlanmis, kucuk harf, kirpilmis (ic bosluklar tek)."""
    return " ".join(term.split()).casefold()


def week_label(d: date) -> str:
    iso = d.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


class EnglishProfileMissing(AppException):
    def __init__(self):
        super().__init__(
            status_code=404,
            error_code="ENGLISH_PROFILE_MISSING",
            message="İngilizce profili henüz oluşturulmadı",
        )


class EnglishService:
    def __init__(self, uow: TaskUnitOfWork, actor: str = "user"):
        self.uow = uow
        self.actor = actor

    def _source(self, given: str | None) -> str:
        return given or ACTOR_SOURCE.get(self.actor, "self")

    async def _today(self, user_id: int) -> tuple[date, datetime, object]:
        tz = await user_tz(self.uow, user_id)
        now = _now()
        return local_today(tz, now), now, tz

    # ---------------- profil ----------------
    async def get_profile(self, user_id: int) -> ProfileResponse:
        entity = await self.uow.english_profiles.for_user(user_id)
        if entity is None:
            raise EnglishProfileMissing()
        return ProfileResponse.model_validate(entity)

    async def put_profile(self, user_id: int, data: ProfileInput) -> ProfileResponse:
        entity = await self.uow.english_profiles.for_user(user_id)
        if entity is None:
            today, _, _ = await self._today(user_id)
            entity = EnglishProfileEntity(user_id=user_id, started_at=today)
            await self.uow.english_profiles.create(entity)
        entity.target_level = data.target_level
        entity.current_level = data.current_level
        entity.daily_minutes = data.daily_minutes
        entity.focus = list(data.focus)
        await self.uow.commit()
        return ProfileResponse.model_validate(entity)

    # ---------------- kelime ----------------
    async def _vocab_owned(self, vocab_id: int, user_id: int) -> EnglishVocabEntity:
        v = await self.uow.english_vocab.get_owned(vocab_id, user_id)
        if v is None:
            raise NotFoundException("Vocab", vocab_id)
        return v

    @staticmethod
    def _vocab_response(entity: EnglishVocabEntity, existing: bool = False) -> VocabResponse:
        out = VocabResponse.model_validate(entity)
        out.existing = existing
        return out

    async def add_vocab(
        self, user_id: int, items: list[VocabItem]
    ) -> list[VocabResponse]:
        today, now, _ = await self._today(user_id)
        out: list[VocabResponse] = []
        for item in items:
            key = term_key(item.term)
            found = await self.uow.english_vocab.by_key(user_id, key)
            if found is not None:
                out.append(self._vocab_response(found, existing=True))
                continue
            card = new_card(today)
            entity = EnglishVocabEntity(
                user_id=user_id,
                term=item.term,
                term_key=key,
                meaning_tr=item.meaning_tr,
                example=item.example,
                source=self._source(item.source),
                ease=card.ease,
                interval_days=card.interval_days,
                reps=card.reps,
                lapses=card.lapses,
                due_on=card.due_on,
                created_at=now,
            )
            await self.uow.english_vocab.create(entity)
            await self.uow.flush()
            out.append(self._vocab_response(entity))
        await self.uow.commit()
        return out

    async def list_vocab(
        self, user_id: int, due: bool, limit: int
    ) -> list[VocabResponse]:
        today, _, _ = await self._today(user_id)
        rows = await self.uow.english_vocab.list_for_user(
            user_id, limit, today if due else None
        )
        return [self._vocab_response(r) for r in rows]

    async def update_vocab(
        self, vocab_id: int, user_id: int, patch: VocabUpdate
    ) -> VocabResponse:
        entity = await self._vocab_owned(vocab_id, user_id)
        fields = patch.model_dump(exclude_unset=True)
        if fields.get("term") is not None:
            key = term_key(fields["term"])
            clash = await self.uow.english_vocab.by_key(user_id, key)
            if clash is not None and clash.id != entity.id:
                raise ConflictException(
                    "ENGLISH_VOCAB_EXISTS", "Bu kelime zaten kayıtlı"
                )
            entity.term, entity.term_key = fields["term"], key
        if fields.get("meaning_tr") is not None:
            entity.meaning_tr = fields["meaning_tr"]
        if "example" in fields:
            entity.example = fields["example"]
        await self.uow.commit()
        return self._vocab_response(entity)

    async def delete_vocab(self, vocab_id: int, user_id: int) -> None:
        entity = await self._vocab_owned(vocab_id, user_id)
        await self.uow.english_vocab.delete(entity)
        await self.uow.commit()

    async def review_vocab(
        self, vocab_id: int, user_id: int, grade: int
    ) -> VocabResponse:
        entity = await self._vocab_owned(vocab_id, user_id)
        today, now, _ = await self._today(user_id)
        card = SrsCard(
            ease=entity.ease,
            interval_days=entity.interval_days,
            reps=entity.reps,
            lapses=entity.lapses,
            due_on=entity.due_on,
            last_reviewed_at=entity.last_reviewed_at,
        )
        out = review(card, grade, today, now)
        entity.ease = out.ease
        entity.interval_days = out.interval_days
        entity.reps = out.reps
        entity.lapses = out.lapses
        entity.due_on = out.due_on
        entity.last_reviewed_at = out.last_reviewed_at
        await self.uow.commit()
        return self._vocab_response(entity)

    # ---------------- hata gunlugu ----------------
    async def add_mistakes(
        self, user_id: int, items: list[MistakeItem]
    ) -> list[EnglishMistakeEntity]:
        now = _now()
        created = []
        for item in items:
            entity = EnglishMistakeEntity(
                user_id=user_id,
                source=self._source(item.source),
                original=item.original,
                corrected=item.corrected,
                category=item.category,
                explanation_tr=item.explanation_tr,
                review_count=0,
                created_at=now,
            )
            await self.uow.english_mistakes.create(entity)
            created.append(entity)
        await self.uow.commit()
        return created

    async def list_mistakes(
        self, user_id: int, category: str | None, limit: int
    ) -> list[EnglishMistakeEntity]:
        return await self.uow.english_mistakes.list_for_user(user_id, limit, category)

    async def delete_mistake(self, mistake_id: int, user_id: int) -> None:
        entity = await self.uow.english_mistakes.get_owned(mistake_id, user_id)
        if entity is None:
            raise NotFoundException("Mistake", mistake_id)
        await self.uow.english_mistakes.delete(entity)
        await self.uow.commit()

    # ---------------- seanslar ----------------
    async def add_session(
        self, user_id: int, data: SessionCreate
    ) -> EnglishSessionEntity:
        now = _now()
        entity = EnglishSessionEntity(
            user_id=user_id,
            kind=data.kind,
            started_at=data.started_at or now,
            minutes=data.minutes,
            summary=data.summary,
            new_vocab=data.new_vocab,
            mistakes_count=data.mistakes_count,
            source=self._source(data.source),
            created_at=now,
        )
        await self.uow.english_sessions.create(entity)
        await self.uow.commit()
        return entity

    async def list_sessions(self, user_id: int, limit: int):
        return await self.uow.english_sessions.list_for_user(user_id, limit)

    async def practiced_on(self, user_id: int, day: date) -> bool:
        tz = await user_tz(self.uow, user_id)
        start, end = day_bounds(day, tz)
        return bool(await self.uow.english_sessions.in_range(user_id, start, end))

    async def daily_minutes(self, user_id: int) -> int | None:
        """Profil varsa gunluk hedef dakika (gun plani onerisi icin), yoksa None."""
        profile = await self.uow.english_profiles.for_user(user_id)
        return profile.daily_minutes if profile else None

    # ---------------- bugun ----------------
    async def today(self, user_id: int) -> TodayResponse:
        today, _, tz = await self._today(user_id)
        profile = await self.uow.english_profiles.for_user(user_id)
        due = await self.uow.english_vocab.list_for_user(user_id, DUE_IN_TODAY, today)
        since = day_bounds(today - timedelta(days=6), tz)[0]
        counts = Counter(m.category for m in await self.uow.english_mistakes.since(user_id, since))
        top = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:3]
        task = None
        if profile is not None and profile.focus:
            task = TASK_TEXTS[profile.focus[today.toordinal() % len(profile.focus)]]
        return TodayResponse(
            profile=ProfileResponse.model_validate(profile) if profile else None,
            due_vocab=[self._vocab_response(v) for v in due],
            top_categories=[CategoryCount(category=c, count=n) for c, n in top],
            practiced_today=await self.practiced_on(user_id, today),
            task=task,
        )

    # ---------------- ilerleme ----------------
    async def progress(self, user_id: int, weeks: int) -> ProgressResponse:
        today, _, tz = await self._today(user_id)
        monday = today - timedelta(days=today.weekday())
        first_monday = monday - timedelta(weeks=weeks - 1)
        range_start = day_bounds(first_monday, tz)[0]

        # seri: bugunden (seans yoksa dunden) geriye kesintisiz gun sayisi
        days = {s.astimezone(tz).date() for s in await self.uow.english_sessions.all_starts(user_id)}
        cursor = today if today in days else today - timedelta(days=1)
        streak = 0
        while cursor in days:
            streak += 1
            cursor -= timedelta(days=1)

        minutes: dict[str, int] = {
            week_label(first_monday + timedelta(weeks=i)): 0 for i in range(weeks)
        }
        for s in await self.uow.english_sessions.in_range(user_id, range_start):
            key = week_label(s.started_at.astimezone(tz).date())
            if key in minutes:
                minutes[key] += s.minutes

        by_cat: Counter[tuple[str, str]] = Counter()
        for m in await self.uow.english_mistakes.since(user_id, range_start):
            by_cat[(week_label(m.created_at.astimezone(tz).date()), m.category)] += 1

        total, due, mature = await self.uow.english_vocab.stats(user_id, today)
        return ProgressResponse(
            streak_days=streak,
            weekly_minutes=[WeekMinutes(week=w, minutes=n) for w, n in minutes.items()],
            vocab_stats=VocabStats(total=total, due=due, mature=mature),
            mistakes_by_category=[
                WeekCategoryCount(week=w, category=c, count=n)
                for (w, c), n in sorted(by_cat.items())
                if w in minutes
            ],
        )
