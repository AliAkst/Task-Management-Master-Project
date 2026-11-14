"""Faz 13e — G1: tamamlanma iddiası sınıflandırıcısı (düşman girdi tablosu)."""

import pytest

from app.agent.guard import NOOP_WARNING, PENDING_WARNING, TurnFacts, check_reply

P, N, X = PENDING_WARNING, NOOP_WARNING, None

# (metin, pending, executed_writes, beklenen)
CASES = [
    ("Kartı ekledim!", 1, 0, P),
    ("Kartı ekledim!", 0, 0, N),
    ("Kartı ekledim!", 0, 1, X),
    ("Takvime koydum, iyi çalışmalar.", 1, 0, P),
    ("Planını oluşturdum.", 0, 0, N),
    ("Görev oluşturuldu.", 1, 0, P),
    ("Onaylarsan kartı ekleyeceğim.", 1, 0, X),
    ("Onay kartından kontrol et; onaylayınca eklenecek.", 1, 0, X),
    ("Dün spor yaptım dedin, harika!", 0, 0, X),
    ("Ben de bugün kahve içtim.", 0, 0, X),
    ("Kartı henüz eklemedim.", 0, 0, X),
    ("Spor yaptın mı?", 0, 0, X),
    ("Hallettim, takvimde görebilirsin.", 0, 0, N),
    ("Listeyi güncelledim. Başka bir şey?", 1, 0, P),
    ("P2 kartını taşıdım. Ayrıca yarın için öneri: erken kalk. İyi geceler.", 1, 0, X),
    ("Kaydedildi: haftalık hedefin 5 saat.", 0, 0, X),
    ("Etkinlik silindi.", 0, 0, N),
    ("Eklediğim kart duruyor mu bakalım", 0, 0, X),
    ("Ekledim ama onaylaman gerekiyor, henüz yapılmadı.", 1, 0, X),
    ("Planı ayarladım", 2, 0, P),
    ("", 1, 0, X),
    ("Notunu karta yazdım.", 0, 1, X),
    # Kabul edilen yanlış pozitif: "açtım"/"baktım" gerçek değişiklik olmadan da
    # uygulama nesnesiyle geçiyor; uyarı zararsız (yalnız bir not düşer).
    ("Kartını açtım, takvimine baktım.", 0, 0, N),
]


@pytest.mark.parametrize("reply,pending,executed,expected", CASES)
def test_check_reply_table(reply, pending, executed, expected):
    assert check_reply(reply, TurnFacts(pending, executed)) == expected


def test_table_has_23_rows():
    assert len(CASES) == 23
