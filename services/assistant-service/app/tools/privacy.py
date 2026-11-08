"""
Gizlilik filtresi: aktif model cloud ise `local_only` board'larin verisi (board,
kartlari, takvim ogeleri, plan maddeleri, istatistik satirlari) arac
sonuclarindan cikarilir. Model local ise filtre hicbir sey yapmaz.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PrivacyFilter:
    active: bool = False  # True = cloud model, filtre uygulanir
    hidden_boards: set[int] = field(default_factory=set)
    hidden_cards: set[int] = field(default_factory=set)

    def board_hidden(self, board_id: Any) -> bool:
        return self.active and board_id in self.hidden_boards

    def card_hidden(self, card_id: Any) -> bool:
        return self.active and card_id in self.hidden_cards

    def keep(self, item: dict[str, Any]) -> bool:
        """board_id / card_id alanlarindan biri gizliyse ogeyi at."""
        if not self.active:
            return True
        return not (
            self.board_hidden(item.get("board_id"))
            or self.card_hidden(item.get("card_id"))
        )

    def filter(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [i for i in items if self.keep(i)]


HIDDEN_MESSAGE = (
    "Bu veri gizli: kullanıcı bu board'u sadece local modelin görmesine izin verdi. "
    "Kullanıcıya bunu söyle ve local modele geçmesini öner."
)
