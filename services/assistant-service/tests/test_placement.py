"""Faz 13d — yerleştirme motoru: kural tablosu P1–P12, soru metinleri Q1–Q5, V1–V3."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from app.tools.placement import (
    Busy,
    Placement,
    Question,
    TemplateInfo,
    apply_patch,
    day_question,
    place_day,
)
from app.tools.schedule_day import hhmm

TZ = ZoneInfo("Europe/Istanbul")
DAY = date(2026, 11, 17)  # Salı, bugün değil
NOW = datetime(2026, 11, 14, 12, 0, tzinfo=TZ)


def run(items, *, template=None, busy=None, now=NOW, day=DAY, **kw):
    return place_day(
        items, day=day, now_local=now, template=template, busy=busy or [], **kw
    )


def times(p: Placement):
    return [(r.title, hhmm(r.start), hhmm(r.end)) for r in p.rows]


def ev_busy(title, s, e):
    return Busy(title, s * 60, e * 60, "event")


def ev_home():
    """V3: Ev günü şablonu."""
    return TemplateInfo(
        "Ev günü",
        [
            Busy("Mesai", 540, 720, "template"),
            Busy("Öğle arası", 720, 780, "template"),
            Busy("Mesai", 780, 1080, "template"),
        ],
        480,
        1380,
        0,
    )


# ---------------------------------------------------------------- P1
def test_p1_title_required_and_limits():
    with pytest.raises(ValueError, match="1. bloğun başlığı"):
        run([{"minutes": 30}])
    with pytest.raises(ValueError, match="En az bir blok"):
        run([])
    with pytest.raises(ValueError, match="En fazla 24 blok"):
        run([{"title": f"i{n}", "minutes": 5} for n in range(25)])
    p = run([{"title": f"i{n}", "minutes": 5} for n in range(24)])
    assert isinstance(p, Placement) and len(p.rows) == 24


def test_p1_clock_and_minutes_messages_match_build_timeline():
    with pytest.raises(ValueError, match="geçerli bir saat değil"):
        run([{"title": "A", "start": "25:00"}])
    with pytest.raises(ValueError, match="HH:MM olmalı"):
        run([{"title": "A", "start": "yedi"}])
    with pytest.raises(ValueError, match="1–1440 dakika"):
        run([{"title": "A", "minutes": 0}])
    with pytest.raises(ValueError, match="minutes tam sayı"):
        run([{"title": "A", "minutes": "x"}])


def test_p1_end_with_minutes_is_anchor_and_end_alone_is_error():
    p = run([{"title": "A", "end": "11:00", "minutes": 45}])
    assert times(p) == [("A", "10:15", "11:00")]
    with pytest.raises(ValueError, match="start ya da minutes ver"):
        run([{"title": "A", "end": "11:00"}])
    with pytest.raises(ValueError, match="başladığı saatte bitiyor"):
        run([{"title": "A", "start": "10:00", "end": "10:00"}])


# ---------------------------------------------------------------- P2
def test_p2_classes_start_only_defaults_to_30_minutes():
    p = run([{"title": "A", "start": "08:00"}])
    (row,) = p.rows
    assert (row.start, row.end, row.defaulted) == (480, 510, True)


def test_p2_untimed_never_placed_and_window_alone_is_untimed():
    p = run(
        [
            {"title": "Market"},
            {"title": "Akşam bir şey", "window": "akşam"},
            {"title": "Spor", "minutes": 30},
        ]
    )
    assert [r.title for r in p.untimed] == ["Market", "Akşam bir şey"]
    assert times(p) == [("Spor", "08:00", "08:30")]


# ---------------------------------------------------------------- P3
def test_p3_after_midnight_anchor_moves_to_next_day():
    p = run(
        [
            {"title": "Film", "start": "23:00", "minutes": 60},
            {"title": "Uyku", "start": "00:30", "minutes": 30},
        ]
    )
    assert isinstance(p, Placement)
    film, uyku = p.rows
    assert (film.start, film.end) == (1380, 1440)
    assert (uyku.start, uyku.end) == (1470, 1500)


def test_p3_first_item_after_midnight_is_not_shifted():
    p = run([{"title": "Nöbet", "start": "00:30", "minutes": 30}])
    assert p.rows[0].start == 30


def test_p3_end_before_start_wraps():
    p = run([{"title": "Parti", "start": "22:00", "end": "01:00"}])
    assert (p.rows[0].start, p.rows[0].end) == (1320, 1500)


# ---------------------------------------------------------------- P4
def test_p4_template_duplicates_are_dropped_with_note():
    t = ev_home()
    p = run(
        [
            {"title": "mesai", "start": "09:00", "end": "12:00", "card": False},
            {"title": "Başka ad", "start": "12:00", "end": "13:00", "card": False},
            {"title": "Kavramlar", "minutes": 60},
        ],
        template=t,
    )
    assert isinstance(p, Placement)
    assert [r.title for r in p.rows] == ["Kavramlar"]
    assert "'mesai' şablonda zaten var" in p.notes
    assert "'Başka ad' şablonda zaten var" in p.notes


# ---------------------------------------------------------------- P5
def test_p5_same_title_event_is_not_an_obstacle():
    p = run(
        [{"title": "Rapor yaz", "start": "13:30", "minutes": 60}],
        busy=[ev_busy("rapor yaz", 13, 15)],
    )
    assert isinstance(p, Placement)
    assert times(p) == [("Rapor yaz", "13:30", "14:30")]


def test_p5_no_template_means_no_template_obstacles():
    p = run([{"title": "A", "start": "10:00", "minutes": 30}], template=None)
    assert isinstance(p, Placement)


# ---------------------------------------------------------------- P6
def test_p6_template_day_window_and_today_rounding():
    t = TemplateInfo("T", [], 600, 720, 0)  # 10:00-12:00
    p = run([{"title": "A", "minutes": 30}], template=t)
    assert times(p) == [("A", "10:00", "10:30")]
    today = datetime(2026, 11, 17, 13, 7, tzinfo=TZ)
    p = run([{"title": "A", "minutes": 30}], now=today)
    assert times(p) == [("A", "13:10", "13:40")]  # 5 dk yukarı yuvarlanır


def test_p6_default_window_is_08_to_23():
    p = run([{"title": "A", "minutes": 900}])  # 08:00-23:00 tam sığar
    assert times(p) == [("A", "08:00", "23:00")]
    q = run([{"title": "A", "minutes": 901}])
    assert isinstance(q, Question) and q.kind == "q4"


# ---------------------------------------------------------------- P7 / Q1-Q3
def test_p7_q1_anchor_vs_anchor_text_and_options():
    q = run(
        [
            {"title": "A", "start": "10:00", "minutes": 60},
            {"title": "B", "start": "10:30", "minutes": 60},
        ]
    )
    assert isinstance(q, Question) and q.kind == "q1"
    assert q.text.splitlines() == [
        "«B» 10:30–11:30, «A» 10:00–11:00 ile çakışıyor.",
        "1) «B» → 11:00 sonrasına",
        "2) «B» → ilk boş saate",
        "3) İkisi de bu saatlerde kalsın",
        'Numarayla cevap ver (ör. 1) ya da "vazgeç" yaz.',
    ]
    assert len(q.options) == 3


def test_q1_options_resolve_the_conflict():
    items = [
        {"title": "A", "start": "10:00", "minutes": 60},
        {"title": "B", "start": "10:30", "minutes": 60},
    ]
    q = run(items)
    state = {"items": items, "template_off": False, "unfit": None, "day": DAY.isoformat()}
    # 1: B, A'nın bitişine
    s1 = apply_patch(state, q.options[0].patch)
    assert times(run(s1["items"])) == [("A", "10:00", "11:00"), ("B", "11:00", "12:00")]
    # 2: esnek -> listedeki önceki öğenin (A) bitişinden devam eder (P9)
    s2 = apply_patch(state, q.options[1].patch)
    placed = run(s2["items"])
    assert isinstance(placed, Placement)
    assert times(placed) == [("A", "10:00", "11:00"), ("B", "11:00", "12:00")]
    # 3: ikisi de kalsın
    s3 = apply_patch(state, q.options[2].patch)
    both = run(s3["items"])
    assert isinstance(both, Placement)
    assert times(both) == [("A", "10:00", "11:00"), ("B", "10:30", "11:30")]


def test_p7_q2_anchor_vs_calendar_event_text():
    q = run(
        [{"title": "İş", "start": "09:00", "end": "12:00"}],
        busy=[ev_busy("Toplantı", 10, 11)],
    )
    assert isinstance(q, Question) and q.kind == "q2"
    assert q.text.splitlines()[:4] == [
        "«İş» 09:00–12:00, takvimdeki «Toplantı» 10:00–11:00 ile çakışıyor.",
        "1) «İş» → 11:00 sonrasına",
        "2) «İş» → ilk boş saate",
        "3) Çakışsın, bu saatte kalsın",
    ]


def test_q2_option1_adds_buffer():
    t = TemplateInfo("T", [], 480, 1380, 10)
    items = [{"title": "İş", "start": "09:30", "minutes": 60}]
    q = run(items, busy=[ev_busy("Toplantı", 10, 11)], template=t)
    assert q.options[0].label == "«İş» → 11:10 sonrasına"
    assert q.options[0].patch["set"]["start"] == "11:10"


def test_p7_q3_anchor_vs_template_text_and_template_off_option():
    q = run(
        [{"title": "Spor", "start": "10:00", "minutes": 60}], template=ev_home()
    )
    assert isinstance(q, Question) and q.kind == "q3"
    assert q.text.splitlines()[:4] == [
        "«Spor» 10:00–11:00, «Ev günü» şablonundaki «Mesai» 09:00–12:00 ile çakışıyor.",
        "1) «Spor» → 12:00 sonrasına",
        "2) Şablon bloğunun içinde kalsın",
        "3) Bu gün şablonu kullanma",
    ]
    assert q.options[2].patch == {"template_off": True}


def test_p7_overlap_ok_skips_check():
    p = run(
        [
            {"title": "A", "start": "10:00", "minutes": 60},
            {"title": "B", "start": "10:30", "minutes": 60, "overlap_ok": True},
        ]
    )
    assert isinstance(p, Placement) and len(p.rows) == 2


def test_p7_past_anchor_today_raises():
    now = datetime(2026, 11, 17, 15, 0, tzinfo=TZ)
    with pytest.raises(ValueError, match="'Sabah koşusu' saati geçti"):
        run([{"title": "Sabah koşusu", "start": "07:00", "minutes": 30}], now=now)


# ---------------------------------------------------------------- P8
def test_p8_lead_in_goes_right_before_first_anchor():
    p = run(
        [
            {"title": "Kavramlar", "minutes": 60},
            {"title": "İş", "start": "09:00", "end": "12:00"},
        ]
    )
    assert times(p) == [("Kavramlar", "08:00", "09:00"), ("İş", "09:00", "12:00")]


def test_p8_lead_in_ignores_day_start_bound():
    t = TemplateInfo("T", [], 480, 1380, 0)
    p = run(
        [
            {"title": "Yol", "minutes": 120},
            {"title": "İş", "start": "09:00", "end": "12:00"},
        ],
        template=t,
    )
    assert times(p) == [("Yol", "07:00", "09:00"), ("İş", "09:00", "12:00")]


def test_p8_blocked_lead_in_falls_back_to_normal_placement():
    p = run(
        [
            {"title": "Kavramlar", "minutes": 60},
            {"title": "İş", "start": "09:00", "end": "12:00"},
        ],
        busy=[ev_busy("Kahvaltı", 8, 9)],
    )
    assert isinstance(p, Placement)
    kav = next(r for r in p.rows if r.title == "Kavramlar")
    assert (kav.start, kav.end) != (480, 540)
    assert kav.start >= 0


def test_p8_lead_in_negative_start_falls_back():
    p = run(
        [
            {"title": "Yol", "minutes": 120},
            {"title": "Nöbet", "start": "01:00", "minutes": 60},
        ]
    )
    assert isinstance(p, Placement)
    assert all(r.start >= 0 for r in p.rows)


# ---------------------------------------------------------------- P9
def test_p9_flex_follow_given_order_after_cursor():
    p = run(
        [
            {"title": "A", "minutes": 30},
            {"title": "B", "minutes": 45},
            {"title": "C", "minutes": 15},
        ]
    )
    assert times(p) == [("A", "08:00", "08:30"), ("B", "08:30", "09:15"), ("C", "09:15", "09:30")]


def test_p9_obstacle_pushes_with_buffer_and_marks_moved():
    t = TemplateInfo("T", [Busy("Mesai", 540, 720, "template")], 480, 1380, 10)
    p = run([{"title": "A", "minutes": 90}], template=t)
    (row,) = p.rows
    assert (hhmm(row.start), hhmm(row.end), row.moved) == ("12:10", "13:40", True)


def test_p9_window_start_and_cursor_not_rewound():
    p = run(
        [
            {"title": "Koşu", "minutes": 45, "window": "akşam"},
            {"title": "Kitap", "minutes": 30},
        ]
    )
    koşu, kitap = p.rows[0], p.rows[1]
    assert (hhmm(koşu.start), hhmm(koşu.end)) == ("18:00", "18:45")
    assert kitap.start >= 18 * 60 + 45  # imleç geri alınmaz


# ---------------------------------------------------------------- P10
def test_p10_windows():
    cases = {
        "sabah": "08:00",  # 06:00-12:00 ∩ gün başlangıcı 08:00
        "öğle": "12:00",
        "öğleden sonra": "14:00",
        "akşam": "18:00",
    }
    for w, start in cases.items():
        p = run([{"title": "X", "minutes": 30, "window": w}])
        assert hhmm(p.rows[0].start) == start, w


def test_p10_night_window_may_pass_day_end():
    p = run([{"title": "X", "minutes": 60, "window": "gece"}])
    assert times(p) == [("X", "22:00", "23:00")]


def test_p10_unknown_window_is_ignored_with_note():
    p = run([{"title": "X", "minutes": 30, "window": "kuşluk"}])
    assert times(p) == [("X", "08:00", "08:30")]
    assert "'X' için pencere anlaşılmadı" in p.notes


def test_p10_window_overflow_goes_unfit():
    p = run([{"title": "X", "minutes": 400, "window": "akşam"}])
    assert isinstance(p, Question) and p.kind == "q4"


# ---------------------------------------------------------------- P11 / Q4
def full_day_items():
    return [{"title": "Uzun", "minutes": 880}, {"title": "Sığmaz", "minutes": 60}]


def test_p11_q4_text_and_four_options_for_single_unfit():
    q = run(
        [{"title": "Uzun", "minutes": 840}, {"title": "Sığmaz", "minutes": 90}]
    )
    assert isinstance(q, Question) and q.kind == "q4"
    lines = q.text.splitlines()
    assert lines[0] == "Şunlar Salı 17 Kasım için boş zamana sığmadı: «Sığmaz» (90 dk)."
    assert lines[1:5] == [
        "1) Saatsiz olarak bu günün planına ekle",
        "2) Yarının (Çarşamba 18 Kasım) planına aktar",
        "3) Plandan çıkar",
        "4) «Sığmaz» → 60 dk'ya kısalt",
    ]
    assert q.options[3].patch == {"item": 1, "set": {"minutes": 60}}


def test_p11_q4_has_no_shorten_option_for_several_unfit():
    q = run(
        [
            {"title": "Uzun", "minutes": 880},
            {"title": "A", "minutes": 60},
            {"title": "B", "minutes": 60},
        ]
    )
    assert isinstance(q, Question)
    assert "«A» (60 dk), «B» (60 dk)" in q.text
    assert len(q.options) == 3


@pytest.mark.parametrize("mode", ["untimed", "carry", "drop"])
def test_p11_unfit_modes(mode):
    p = run(full_day_items(), unfit=mode)
    assert isinstance(p, Placement)
    assert [r.title for r in p.rows] == ["Uzun"]
    assert [r.title for r in p.untimed] == (["Sığmaz"] if mode == "untimed" else [])
    assert [r.title for r in p.carry] == (["Sığmaz"] if mode == "carry" else [])
    if mode == "drop":
        assert "çıkarıldı: Sığmaz" in p.notes


# ---------------------------------------------------------------- P12
def test_p12_rows_sorted_by_start_untimed_keep_given_order():
    p = run(
        [
            {"title": "Z", "start": "15:00", "minutes": 30},
            {"title": "S1"},
            {"title": "A", "start": "09:00", "minutes": 30},
            {"title": "S2"},
        ]
    )
    assert [r.title for r in p.rows] == ["A", "Z"]
    assert [r.title for r in p.untimed] == ["S1", "S2"]


# ---------------------------------------------------------------- Q5
def test_q5_day_question():
    q = day_question([date(2026, 11, 17), date(2026, 11, 14), date(2026, 11, 14)])
    assert q.kind == "q5"
    assert q.text.splitlines() == [
        "Hangi gün için planlayayım?",
        "1) Cumartesi 14 Kasım",
        "2) Salı 17 Kasım",
        'Numarayla cevap ver (ör. 1) ya da "vazgeç" yaz.',
    ]
    assert q.options[1].patch == {"day": "2026-11-17"}


def test_apply_patch_does_not_mutate_original():
    state = {"items": [{"title": "A", "start": "10:00"}], "template_off": False, "unfit": None, "day": "x"}
    new = apply_patch(state, {"item": 0, "set": {"start": None, "minutes": 30}})
    assert state["items"][0] == {"title": "A", "start": "10:00"}
    assert new["items"][0] == {"title": "A", "minutes": 30}
    assert apply_patch(state, {"template_off": True})["template_off"] is True
    assert apply_patch(state, {"unfit": "carry"})["unfit"] == "carry"
    assert apply_patch(state, {"day": "2026-01-01"})["day"] == "2026-01-01"


# ---------------------------------------------------------------- gerçek vaka fikstürleri
V1 = [
    {"title": "İş (Evden Çalışma)", "start": "09:00", "end": "12:00", "card": False},
    {"title": "Kavramlar", "minutes": 60, "card": True},
    {"title": "İş (Evden Çalışma)", "start": "13:00", "end": "18:00", "card": False},
    {"title": "Spor", "minutes": 60, "card": True},
]


def test_v1_sixty_minutes_fits_between_work_blocks():
    p = run(V1)
    assert times(p) == [
        ("İş (Evden Çalışma)", "09:00", "12:00"),
        ("Kavramlar", "12:00", "13:00"),
        ("İş (Evden Çalışma)", "13:00", "18:00"),
        ("Spor", "18:00", "19:00"),
    ]


def test_v1_ninety_minutes_moves_after_work():
    items = [dict(i) for i in V1]
    items[1]["minutes"] = 90
    p = run(items)
    assert times(p) == [
        ("İş (Evden Çalışma)", "09:00", "12:00"),
        ("İş (Evden Çalışma)", "13:00", "18:00"),
        ("Kavramlar", "18:00", "19:30"),
        ("Spor", "19:30", "20:30"),
    ]
    kav = next(r for r in p.rows if r.title == "Kavramlar")
    assert kav.moved is True


def test_v2_calendar_conflict_is_a_question():
    q = run(
        [{"title": "İş", "start": "09:00", "end": "12:00"}],
        busy=[Busy("Toplantı", 600, 630, "event")],
    )
    assert isinstance(q, Question) and q.kind == "q2"


def test_v3_home_template_with_flex_untimed_and_window():
    p = run(
        [
            {"title": "Faruk abi", "minutes": 60, "card": True},
            {"title": "P2", "card": True},
            {"title": "Koşu", "minutes": 45, "window": "akşam", "card": True},
        ],
        template=ev_home(),
    )
    assert isinstance(p, Placement)
    assert times(p) == [("Faruk abi", "08:00", "09:00"), ("Koşu", "18:00", "18:45")]
    assert [r.title for r in p.untimed] == ["P2"]
