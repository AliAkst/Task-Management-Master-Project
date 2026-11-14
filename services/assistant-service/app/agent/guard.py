"""
Faz 13e — "yaptim" korumasi (saf).

Asistan onay bekleyen ya da hic yapilmamis bir ise "ekledim/yaptim" derse uygulama
bunu ayni balonun altinda duzeltir. Siniflandirici bilerek dar tutulur: yalniz son
2 cumle, uygulama nesnesi sozcugu sart, olumsuzlama/kosul varsa iddia sayilmaz.
"""

import re
from dataclasses import dataclass

PENDING_WARNING = "⚠ Henüz yapılmadı: onay kartını onaylarsan uygulanacak."
NOOP_WARNING = "⚠ Bu turda hiçbir değişiklik yapılmadı."

_ROOTS = (
    "ekle|oluştur|planla|taşı|sil|kaydet|tamamla|güncelle|ayarla|koy|ertele|aktar"
    "|yerleştir|işle|hallet|kur|aç|bağla|yaz"
)
_V = "[ıiuü]"
_CLAIM_WORD = re.compile(
    rf"(?:{_ROOTS})(?:[dt]{_V}m|{_V}?[nl][dt]{_V})"
    r"|kaydedildi|halledildi|güncellendi"
)
# Kendi basina yeterli sabit ifadeler (nesne sozcugu aranmaz)
_SELF_CONTAINED = ("işlem tamam", "hepsi hazır")
_OTHER_PHRASES = ("tamamdır, ekledim", "takvime işledim")
_OBJECT = re.compile(
    r"\b(?:kart|takvim|plan|liste|board|etkinlik|görev|hatırlat|gün(?!cel)|madde|not|etiket)"
)
_NEGATION = (
    "onaylarsan",
    "onaylayınca",
    "onaydan sonra",
    "eklenecek",
    "oluşturulacak",
    "ekleyeceğim",
    "ekleyebilirim",
    "eklemedim",
    "yapılmadı",
    "henüz",
)
_SPLIT = re.compile(r"[.!?\n]")
_WORD = re.compile(r"\w+")


@dataclass(frozen=True)
class TurnFacts:
    pending: int  # bu turda onay bekleyen (pending_approval) yazma araci sayisi
    executed_writes: int  # bu turda yapilmis (done) yazma araci sayisi


def _lower(s: str) -> str:
    return s.replace("İ", "i").replace("I", "ı").lower()


def _claims(sentence: str) -> bool:
    s = _lower(sentence)
    if any(n in s for n in _NEGATION):
        return False
    if any(p in s for p in _SELF_CONTAINED):
        return True
    has_claim = any(p in s for p in _OTHER_PHRASES) or any(
        _CLAIM_WORD.fullmatch(w) for w in _WORD.findall(s)
    )
    return has_claim and _OBJECT.search(s) is not None


def check_reply(text: str, turn: TurnFacts) -> str | None:
    """Tamamlanma iddiasi gercekle celisiyorsa uyari metni, yoksa None."""
    sentences = [x for x in (p.strip() for p in _SPLIT.split(text or "")) if x]
    if not any(_claims(s) for s in sentences[-2:]):
        return None
    if turn.pending > 0:
        return PENDING_WARNING
    if turn.executed_writes == 0:
        return NOOP_WARNING
    return None
