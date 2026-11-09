"""Ortak renk paleti (board / etiket renkleri)."""

BOARD_PALETTE = [
    "#64748b",
    "#ef4444",
    "#f97316",
    "#eab308",
    "#22c55e",
    "#14b8a6",
    "#3b82f6",
    "#6366f1",
    "#a855f7",
    "#ec4899",
]


def next_free_color(used: list[str]) -> str:
    """Kullanilmayan ilk palet rengi; hepsi kullaniliyorsa ilk renk."""
    taken = {c.lower() for c in used}
    for color in BOARD_PALETTE:
        if color.lower() not in taken:
            return color
    return BOARD_PALETTE[0]
