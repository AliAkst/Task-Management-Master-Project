"""Faz 13j1: SM-2 aralikli tekrar - saf fonksiyon, tablo testi (saat enjekte edilir)."""

from datetime import UTC, date, datetime

import pytest

from app.services.srs import SrsCard, new_card, review

TODAY = date(2026, 11, 18)
NOW = datetime(2026, 11, 18, 9, 0, tzinfo=UTC)


def card(reps=0, interval=0, ease=2.5, lapses=0) -> SrsCard:
    return SrsCard(
        ease=ease, interval_days=interval, reps=reps, lapses=lapses, due_on=TODAY
    )


def test_new_card_defaults():
    c = new_card(TODAY)
    assert (c.ease, c.interval_days, c.reps, c.lapses, c.due_on) == (2.5, 0, 0, 0, TODAY)
    assert c.last_reviewed_at is None


# (baslangic, not, reps, aralik, ease, lapses)
TABLE = [
    (card(), 5, 1, 1, 2.6, 0),
    (card(reps=1, interval=1, ease=2.6), 4, 2, 6, 2.6, 0),
    (card(reps=2, interval=6, ease=2.6), 3, 3, 16, 2.46, 0),  # 6*2.6=15.6 -> 16
    (card(reps=3, interval=16, ease=2.46), 5, 4, 39, 2.56, 0),  # 16*2.46=39.36 -> 39
    (card(reps=4, interval=10, ease=2.5), 3, 5, 25, 2.36, 0),  # 25.0 (eski ease ile)
    (card(reps=3, interval=16, ease=2.5, lapses=1), 2, 0, 1, 2.18, 2),
    (card(reps=5, interval=30, ease=2.5), 0, 0, 1, 1.7, 1),
    (card(reps=2, interval=6, ease=1.3), 0, 0, 1, 1.3, 1),  # alt sinir
    (card(reps=2, interval=6, ease=1.35), 3, 3, 8, 1.3, 0),  # 6*1.35=8.1 -> 8, alt sinir
]


@pytest.mark.parametrize("start,grade,reps,interval,ease,lapses", TABLE)
def test_review_table(start, grade, reps, interval, ease, lapses):
    out = review(start, grade, TODAY, NOW)
    assert out.reps == reps
    assert out.interval_days == interval
    assert out.ease == pytest.approx(ease)
    assert out.lapses == lapses
    assert out.last_reviewed_at == NOW
    assert (out.due_on - TODAY).days == interval


def test_half_rounds_up_not_bankers():
    # 10 * 2.5 = 25.0; 2 * 2.25 = 4.5 -> int(x + .5) = 5 (Python round() 4 verirdi)
    out = review(card(reps=3, interval=2, ease=2.25), 4, TODAY, NOW)
    assert out.interval_days == 5


def test_review_does_not_mutate_input():
    start = card(reps=1, interval=1, ease=2.6)
    review(start, 4, TODAY, NOW)
    assert (start.reps, start.interval_days, start.ease) == (1, 1, 2.6)


@pytest.mark.parametrize("grade", [-1, 6])
def test_invalid_grade_rejected(grade):
    with pytest.raises(ValueError):
        review(card(), grade, TODAY, NOW)
