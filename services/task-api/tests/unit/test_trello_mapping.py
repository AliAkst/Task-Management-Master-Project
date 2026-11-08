"""Faz 7a: Trello JSON -> yerel yapi esleme (saf fonksiyonlar, ag yok)."""

import json
from pathlib import Path

from app.integrations.trello import (
    is_done_list_name,
    map_board,
    map_board_color,
)

FIXTURE = Path(__file__).parent.parent / "fixtures" / "trello_board.json"


def load():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_board_color_names_and_hex():
    assert map_board_color({"background": "orange"}) == "#f97316"
    # bilinmeyen ad + hex -> paletteki en yakin renk
    assert map_board_color({"background": "photo", "backgroundColor": "#0079BF"}) in {
        "#3b82f6",
        "#14b8a6",
    }
    assert map_board_color({"background": "photo"}) == "#64748b"
    assert map_board_color(None) == "#64748b"


def test_done_list_names():
    for name in ("Done", " bitti ", "Tamamlandı", "Tamamlanan", "TAMAMLANDI"):
        assert is_done_list_name(name), name
    assert not is_done_list_name("Yapılıyor")


def test_map_board_skips_archived_and_orders():
    mb = map_board(load())
    assert [lst.name for lst in mb.lists] == ["Yapılacak", "Yapılıyor", "Bitti"]
    assert [lst.is_done for lst in mb.lists] == [False, False, True]
    ids = {c.id for c in mb.cards}
    # arsivli kart ve arsivli listedeki kart alinmaz
    assert ids == {"c0", "c1", "c2", "c3", "c4"}
    assert mb.color == "#f97316"
    assert mb.description == "Antrenman ve beslenme işleri"


def test_map_card_details():
    mb = map_board(load())
    c1 = next(c for c in mb.cards if c.id == "c1")
    assert c1.due and c1.due.year == 2026 and c1.due.tzinfo is not None
    assert "**Ekler**" in c1.description
    assert "[Mağaza](https://example.com/shop)" in c1.description
    assert [(i.text, i.done) for i in c1.checklist] == [
        ("Bütçe belirle", True),
        ("Mağazaları karşılaştır", False),
    ]
    # yorumlar eskiden yeniye, "<yazar>, <tarih>: " onekiyle; baska aksiyon tipi yok
    assert [n.content for n in c1.notes] == [
        "Deniz Yılmaz, 2026-11-02: Fiyatlara bak",
        "Deniz Yılmaz, 2026-11-03: Numara 44 daha iyi olabilir",
    ]
    # adsiz + renksiz etiket atlanir; adsiz renkli etiket renk adini alir
    assert {lb.name for lb in mb.labels} == {"Acil", "blue"}
    assert next(c for c in mb.cards if c.id == "c4").due_complete is True


def test_multiple_checklists_get_prefixed():
    data = load()
    card = next(c for c in data["cards"] if c["id"] == "c1")
    card["checklists"].append(
        {
            "id": "cl2",
            "name": "Ek",
            "pos": 2,
            "checkItems": [{"id": "ci3", "name": "Fatura", "state": "incomplete", "pos": 1}],
        }
    )
    mb = map_board(data)
    c1 = next(c for c in mb.cards if c.id == "c1")
    assert [i.text for i in c1.checklist] == [
        "Kontrol: Bütçe belirle",
        "Kontrol: Mağazaları karşılaştır",
        "Ek: Fatura",
    ]
