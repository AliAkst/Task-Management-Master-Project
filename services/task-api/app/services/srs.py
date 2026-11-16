"""SM-2 aralikli tekrar (Faz 13j1) - saf fonksiyonlar, saat disaridan verilir."""

from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta

MIN_EASE = 1.3
START_EASE = 2.5


@dataclass(frozen=True)
class SrsCard:
    ease: float
    interval_days: int
    reps: int
    lapses: int
    due_on: date
    last_reviewed_at: datetime | None = None


def new_card(today: date) -> SrsCard:
    return SrsCard(
        ease=START_EASE, interval_days=0, reps=0, lapses=0, due_on=today
    )


def review(card: SrsCard, grade: int, today: date, now: datetime) -> SrsCard:
    """Notu (0-5) isleyip yeni durumu doner; girdi degismez."""
    if not 0 <= grade <= 5:
        raise ValueError("grade 0-5 olmali")
    if grade < 3:
        reps, lapses, interval = 0, card.lapses + 1, 1
    else:
        reps, lapses = card.reps + 1, card.lapses
        if reps == 1:
            interval = 1
        elif reps == 2:
            interval = 6
        else:
            # aralik GUNCELLENMEDEN onceki ease ile; int(x + .5) = yukari yuvarla
            interval = int(card.interval_days * card.ease + 0.5)
    q = 5 - grade
    ease = max(MIN_EASE, round(card.ease + 0.1 - q * (0.08 + q * 0.02), 2))
    return replace(
        card,
        ease=ease,
        interval_days=interval,
        reps=reps,
        lapses=lapses,
        due_on=today + timedelta(days=interval),
        last_reviewed_at=now,
    )
