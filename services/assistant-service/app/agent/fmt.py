"""Faz 13e — Turkce gun/tarih bicimleme (saf)."""

from datetime import date

WEEKDAYS = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]
MONTHS = [
    "Ocak",
    "Şubat",
    "Mart",
    "Nisan",
    "Mayıs",
    "Haziran",
    "Temmuz",
    "Ağustos",
    "Eylül",
    "Ekim",
    "Kasım",
    "Aralık",
]


def fmt_day_long(d: date) -> str:
    """date(2026, 11, 14) -> 'Cumartesi 14 Kasım'."""
    return f"{WEEKDAYS[d.weekday()]} {d.day} {MONTHS[d.month - 1]}"
