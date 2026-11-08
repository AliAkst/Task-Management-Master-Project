"""
Tekrar kurallari (Faz 6c): RFC 5545 RRULE ("FREQ=WEEKLY;BYDAY=MO,WE,FR").

Kurallar kullanicinin YEREL saatinde acilir: "her pazartesi 07:00" yaz/kis
saatinden bagimsiz olarak yerel 07:00'de kalir. Veritabaninda UTC saklanir.

- Tekrarlayan etkinlik tek satirdir; takvim istenen aralik icin tekrarlari
  sorgu aninda uretir (tekrar basina satir yok).
- Tekrarlayan kart bir seriye (card_series) baglidir; kart tamamlaninca bir
  sonraki kopyasi kuralin bir sonraki tarihiyle acilir (bkz. CardService).
"""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from dateutil.rrule import DAILY, MONTHLY, WEEKLY, YEARLY, rrule, rrulestr

from app.core.exceptions import ValidationException
from app.db.entities import EventEntity
from app.db.unit_of_work import TaskUnitOfWork

ALLOWED_FREQ = {DAILY, WEEKLY, MONTHLY, YEARLY}
MAX_OCCURRENCES = 1000  # tek aralikta bir etkinlik icin ust sinir


def _parse(rule: str, dtstart: datetime) -> rrule:
    return rrulestr(rule, dtstart=dtstart)  # type: ignore[return-value]


def normalize_rule(rule: str | None) -> str | None:
    """Bos -> None. Gecersiz ya da cok sik (saatlik/dakikalik) kural -> 422."""
    if rule is None or not rule.strip():
        return None
    text = rule.strip().upper().removeprefix("RRULE:")
    if "\n" in text or len(text) > 500:
        raise ValidationException("Tekrar kuralı tek satır RRULE olmalı")
    try:
        parsed = _parse(text, datetime(2026, 1, 1))
    except (ValueError, TypeError) as e:
        raise ValidationException(f"Geçersiz tekrar kuralı: {e}") from e
    if parsed._freq not in ALLOWED_FREQ:  # noqa: SLF001
        raise ValidationException(
            "Tekrar günlük, haftalık, aylık ya da yıllık olabilir"
        )
    return text


def _local(dt: datetime, tz: ZoneInfo) -> datetime:
    """UTC -> yerel, saat dilimsiz (rrule yerel duvar saatiyle calisir)."""
    return dt.astimezone(tz).replace(tzinfo=None)


def _utc(naive_local: datetime, tz: ZoneInfo) -> datetime:
    return naive_local.replace(tzinfo=tz).astimezone(UTC)


def occurrences(
    rule: str,
    start: datetime,
    duration: timedelta,
    window: tuple[datetime, datetime],
    tz: ZoneInfo,
) -> list[tuple[datetime, datetime]]:
    """[window) ile kesisen tekrarlar (UTC baslangic, bitis)."""
    w_start, w_end = window
    r = _parse(rule, _local(start, tz))
    # Pencereden once baslayip icine tasan tekrar da gorunsun
    found = r.between(_local(w_start - duration, tz), _local(w_end, tz), inc=True)
    out = []
    for occ in found[:MAX_OCCURRENCES]:
        s = _utc(occ, tz)
        e = s + duration
        if s < w_end and e > w_start:
            out.append((s, e))
    return out


def next_occurrence(
    rule: str, base: datetime, after: datetime, tz: ZoneInfo
) -> datetime | None:
    """`base`'in saatini koruyarak `after`'dan sonraki ilk tekrar (UTC)."""
    nxt = _parse(rule, _local(base, tz)).after(_local(after, tz), inc=False)
    return _utc(nxt, tz) if nxt is not None else None


async def events_in_range(
    uow: TaskUnitOfWork, user_id: int, start: datetime, end: datetime, tz: ZoneInfo
) -> list[tuple[EventEntity, datetime, datetime]]:
    """Araliktaki etkinlikler; tekrarlayanlar acilmis halde (etkinlik, bas, bit)."""
    out = [
        (e, e.start_at, e.end_at)
        for e in await uow.events.in_range(user_id, start, end)
        if not e.recurrence_rule
    ]
    for e in await uow.events.recurring_before(user_id, end):
        for s, f in occurrences(
            e.recurrence_rule,  # type: ignore[arg-type]
            e.start_at,
            e.end_at - e.start_at,
            (start, end),
            tz,
        ):
            out.append((e, s, f))
    out.sort(key=lambda x: (x[1], x[0].id))
    return out
