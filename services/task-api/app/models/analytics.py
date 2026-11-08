from datetime import date

from pydantic import BaseModel


class DayStat(BaseModel):
    date: date
    tracked_min: int = 0
    planned: int = 0  # planli madde sayisi
    done: int = 0
    partial: int = 0
    not_done: int = 0
    postponed: int = 0
    unplanned: int = 0  # plansiz yapilan is
    reviewed: bool = False
    mood: int | None = None
    energy: int | None = None


class BoardStat(BaseModel):
    board_id: int | None
    name: str
    color: str
    tracked_min: int = 0
    completed_cards: int = 0
    # Haftalik hedefin bu araliga orantilanmis hali (dakika)
    budget_min: int | None = None


class EstimateSample(BaseModel):
    card_id: int
    title: str
    estimated_min: int
    tracked_min: int
    ratio: float  # tracked / estimated


class EstimateAccuracy(BaseModel):
    """Tamamlanan, tahmini ve suresi olan kartlarda gercek/tahmin orani."""

    sample_size: int = 0
    mean_ratio: float | None = None  # 1.35 = tahminden %35 uzun suruyor
    median_ratio: float | None = None
    biggest_overruns: list[EstimateSample] = []


class PostponedCard(BaseModel):
    card_id: int
    title: str
    count: int


class Totals(BaseModel):
    days: int
    tracked_min: int = 0
    planned_items: int = 0
    done_items: int = 0
    # Degerlendirilmis planli maddelerden yapilanlarin orani (partial yarim sayilir)
    completion_rate: float | None = None
    reviewed_days: int = 0
    current_streak: int = 0  # bugun/dun biten ardisik degerlendirilmis gunler
    completed_cards: int = 0


class AnalyticsSummary(BaseModel):
    start: date
    end: date
    totals: Totals
    days: list[DayStat]
    boards: list[BoardStat]
    estimate_accuracy: EstimateAccuracy
    productive_hours: list[int]  # 24 eleman, saat basina dakika
    weekdays: list[int]  # 7 eleman (0=Pazartesi), gun basina dakika
    most_postponed: list[PostponedCard]
