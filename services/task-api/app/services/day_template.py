"""Gun sablonlari (Faz 13c): CRUD, gunun sablonu (resolve) ve plana uygulama."""

from datetime import UTC, date, datetime, time

from pydantic import ValidationError

from app.core.exceptions import (
    ConflictException,
    NotFoundException,
    ValidationException,
)
from app.db.entities import DayTemplateEntity
from app.db.entities.day_plan import DayPlanEntity, DayPlanItemEntity, DayPlanStatus
from app.db.unit_of_work import TaskUnitOfWork
from app.models.day_template import (
    ApplyTemplateResult,
    DayTemplateCreate,
    DayTemplateForDay,
    DayTemplateResponse,
    DayTemplateUpdate,
    TemplateModeInput,
    hhmm_to_min,
)
from app.services.nl_when import fold
from app.services.ordering import STEP
from app.services.timeutil import user_tz

MAX_TEMPLATES = 10
WEEKDAY_NAMES = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]


def _now() -> datetime:
    return datetime.now(UTC)


class DayTemplateService:
    def __init__(self, uow: TaskUnitOfWork, actor: str = "user"):
        self.uow = uow
        self.actor = actor

    # ---------------- CRUD ----------------
    async def _owned(self, template_id: int, user_id: int) -> DayTemplateEntity:
        t = await self.uow.day_templates.get_owned(template_id, user_id)
        if t is None:
            raise NotFoundException("DayTemplate", template_id)
        return t

    async def _check_conflicts(
        self,
        user_id: int,
        data: DayTemplateCreate,
        exclude_id: int | None = None,
    ) -> None:
        others = [
            t
            for t in await self.uow.day_templates.list_for_user(user_id)
            if t.id != exclude_id
        ]
        if any(t.name.casefold() == data.name.casefold() for t in others):
            raise ConflictException(
                "TEMPLATE_NAME_TAKEN", f"'{data.name}' adlı bir şablon zaten var"
            )
        for day in data.weekdays:
            for t in others:
                if day in (t.weekdays or []):
                    raise ConflictException(
                        "WEEKDAY_TAKEN",
                        f"{WEEKDAY_NAMES[day]} (weekday={day}) zaten "
                        f"'{t.name}' şablonunda",
                    )

    @staticmethod
    def _fill(entity: DayTemplateEntity, data: DayTemplateCreate) -> None:
        entity.name = data.name
        entity.weekdays = list(data.weekdays)
        entity.blocks = [b.model_dump() for b in data.blocks]
        entity.day_start = data.day_start
        entity.day_end = data.day_end
        entity.buffer_min = data.buffer_min

    async def list(self, user_id: int) -> list[DayTemplateResponse]:
        return [
            DayTemplateResponse.model_validate(t)
            for t in await self.uow.day_templates.list_for_user(user_id)
        ]

    async def create(self, user_id: int, data: DayTemplateCreate) -> DayTemplateResponse:
        existing = await self.uow.day_templates.list_for_user(user_id)
        if len(existing) >= MAX_TEMPLATES:
            raise ConflictException(
                "TOO_MANY_TEMPLATES", f"En fazla {MAX_TEMPLATES} şablon oluşturulabilir"
            )
        await self._check_conflicts(user_id, data)
        entity = DayTemplateEntity(user_id=user_id)
        self._fill(entity, data)
        await self.uow.day_templates.create(entity)
        await self.uow.commit()
        return DayTemplateResponse.model_validate(entity)

    async def update(
        self, template_id: int, user_id: int, patch: DayTemplateUpdate
    ) -> DayTemplateResponse:
        entity = await self._owned(template_id, user_id)
        merged = {
            "name": entity.name,
            "weekdays": entity.weekdays,
            "blocks": entity.blocks,
            "day_start": entity.day_start,
            "day_end": entity.day_end,
            "buffer_min": entity.buffer_min,
        }
        merged.update(patch.model_dump(exclude_unset=True))
        try:
            data = DayTemplateCreate.model_validate(merged)
        except ValidationError as e:
            msg = "; ".join(str(err["msg"]).removeprefix("Value error, ") for err in e.errors())
            raise ValidationException(msg) from e
        await self._check_conflicts(user_id, data, exclude_id=entity.id)
        self._fill(entity, data)
        await self.uow.day_templates.update(entity)
        await self.uow.commit()
        return DayTemplateResponse.model_validate(entity)

    async def delete(self, template_id: int, user_id: int) -> None:
        entity = await self._owned(template_id, user_id)
        # SQLite'ta FK SET NULL calismayabilir: sabitlenmis gunleri elle birak
        for plan in await self.uow.day_plans.with_template(user_id, entity.id):
            plan.template_id = None
        await self.uow.day_templates.delete(entity)
        await self.uow.commit()

    # ---------------- gunun sablonu ----------------
    async def _resolve(
        self, user_id: int, day: date, plan: DayPlanEntity | None
    ) -> tuple[DayTemplateEntity | None, str | None]:
        """Tek kural: off -> override -> hafta gunu -> yok."""
        if plan is not None and plan.template_off:
            return None, "off"
        if plan is not None and plan.template_id is not None:
            t = await self.uow.day_templates.get_owned(plan.template_id, user_id)
            if t is not None:
                return t, "override"
        for t in await self.uow.day_templates.list_for_user(user_id):
            if day.weekday() in (t.weekdays or []):
                return t, "weekday"
        return None, None

    async def for_day(self, user_id: int, day: date) -> DayTemplateForDay:
        plan = await self.uow.day_plans.for_date(user_id, day)
        template, source = await self._resolve(user_id, day, plan)
        return DayTemplateForDay(
            template=DayTemplateResponse.model_validate(template) if template else None,
            source=source,  # type: ignore[arg-type]
            applied_at=plan.template_applied_at if plan else None,
        )

    async def _plan_for_write(self, user_id: int, day: date) -> DayPlanEntity:
        plan = await self.uow.day_plans.for_date(user_id, day)
        if plan is None:
            plan = DayPlanEntity(user_id=user_id, date=day, status=DayPlanStatus.PLANNED)
            await self.uow.day_plans.create(plan)
            await self.uow.flush()
        if plan.status == DayPlanStatus.REVIEWED:
            raise ConflictException(
                "PLAN_ALREADY_REVIEWED", "Bu gün değerlendirildi; şablon değiştirilemez"
            )
        return plan

    async def set_mode(
        self, user_id: int, day: date, data: TemplateModeInput
    ) -> DayTemplateForDay:
        if data.mode == "template":
            await self._owned(data.template_id, user_id)  # type: ignore[arg-type]
        plan = await self._plan_for_write(user_id, day)
        if data.mode == "auto":
            plan.template_id, plan.template_off = None, False
        elif data.mode == "off":
            plan.template_off = True
        else:
            plan.template_id, plan.template_off = data.template_id, False
        await self.uow.commit()
        return await self.for_day(user_id, day)

    async def apply(
        self, user_id: int, day: date, force: bool = False
    ) -> ApplyTemplateResult:
        plan = await self.uow.day_plans.for_date(user_id, day)
        if plan is not None and plan.status == DayPlanStatus.REVIEWED:
            raise ConflictException(
                "PLAN_ALREADY_REVIEWED", "Bu gün değerlendirildi; şablon eklenemez"
            )
        template, _ = await self._resolve(user_id, day, plan)
        if template is None:
            return ApplyTemplateResult(added=0, reason="no_template")
        if plan is not None and plan.template_applied_at is not None and not force:
            return ApplyTemplateResult(added=0, reason="already_applied")

        plan = await self._plan_for_write(user_id, day)
        tz = await user_tz(self.uow, user_id)
        existing = await self.uow.day_plan_items.for_plans([plan.id])
        titles = {fold(i.title) for i in existing}
        position = max((i.position for i in existing), default=0.0)
        added = 0
        for b in sorted(template.blocks or [], key=lambda x: hhmm_to_min(x["start"])):
            key = fold(b["title"])
            if key in titles:
                continue
            titles.add(key)
            s_min, e_min = hhmm_to_min(b["start"]), hhmm_to_min(b["end"])
            start = datetime.combine(
                day, time(s_min // 60, s_min % 60), tzinfo=tz
            ).astimezone(UTC)
            position += STEP
            await self.uow.day_plan_items.create(
                DayPlanItemEntity(
                    user_id=user_id,
                    day_plan_id=plan.id,
                    title=b["title"][:200],
                    was_planned=True,
                    planned_start=start,
                    planned_minutes=e_min - s_min,
                    position=position,
                    source="template",
                )
            )
            added += 1
        plan.template_applied_at = _now()
        await self.uow.commit()
        return ApplyTemplateResult(added=added, reason="applied")
