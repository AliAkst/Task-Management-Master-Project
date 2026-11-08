"""
Kanban siralama yardimcisi.

Pozisyonlar float tutulur: bir ogeyi iki komsunun arasina koymak icin sadece
o ogenin pozisyonu degisir (ortalama). Aralik cok daralirsa (art arda ayni
yere bir suru tasima) tum liste 1024'luk adimlarla yeniden numaralanir.
"""

from typing import Protocol

STEP = 1024.0
MIN_GAP = 1e-6


class Positioned(Protocol):
    position: float


def place_at(siblings: list[Positioned], item: Positioned, index: int) -> None:
    """
    `item`'i, sirali `siblings` listesinde (item'in kendisi HARIC) `index`
    konumuna yerlestirir; gerekli pozisyon degisikliklerini nesnelere yazar.
    """
    index = max(0, min(index, len(siblings)))
    before = siblings[index - 1].position if index > 0 else None
    after = siblings[index].position if index < len(siblings) else None

    if before is None and after is None:
        item.position = STEP
        return
    if after is None:
        item.position = before + STEP  # type: ignore[operator]
        return
    if before is None:
        if after > MIN_GAP * 2:
            item.position = after / 2
            return
    elif after - before > MIN_GAP:
        item.position = (before + after) / 2
        return

    # Aralik kalmadi -> yeniden numaralandir
    ordered = [*siblings[:index], item, *siblings[index:]]
    for i, obj in enumerate(ordered, start=1):
        obj.position = i * STEP
