from dataclasses import dataclass

from app.services.ordering import STEP, place_at


@dataclass
class Item:
    name: str
    position: float = 0.0


def ordered(items: list[Item]) -> list[str]:
    return [i.name for i in sorted(items, key=lambda i: i.position)]


def make(*names: str) -> list[Item]:
    return [Item(n, (i + 1) * STEP) for i, n in enumerate(names)]


def test_empty_list():
    item = Item("x")
    place_at([], item, 0)
    assert item.position == STEP


def test_append_to_end():
    siblings = make("a", "b")
    item = Item("x")
    place_at(siblings, item, 99)  # index sona kirpilir
    assert ordered([*siblings, item]) == ["a", "b", "x"]


def test_insert_front_and_middle():
    siblings = make("a", "b")
    front = Item("f")
    place_at(siblings, front, 0)
    assert ordered([*siblings, front]) == ["f", "a", "b"]

    siblings = make("a", "b")
    mid = Item("m")
    place_at(siblings, mid, 1)
    assert ordered([*siblings, mid]) == ["a", "m", "b"]
    # sadece tasinan ogenin pozisyonu degisir
    assert [s.position for s in siblings] == [STEP, 2 * STEP]


def test_renumbers_when_gap_exhausted():
    siblings = [Item("a", 1.0), Item("b", 1.0 + 1e-9)]
    item = Item("x")
    place_at(siblings, item, 1)
    assert ordered([*siblings, item]) == ["a", "x", "b"]
    assert [
        i.position for i in sorted([*siblings, item], key=lambda i: i.position)
    ] == [
        STEP,
        2 * STEP,
        3 * STEP,
    ]


def test_many_inserts_at_same_spot_stay_ordered():
    siblings = make("a", "b")
    names = ["a"]
    for n in range(80):  # 80 kez ayni araliga ekle -> en az bir kez renumber
        item = Item(f"x{n}")
        place_at(sorted(siblings, key=lambda i: i.position), item, 1)
        siblings.append(item)
        names.insert(1, f"x{n}")
    names.append("b")
    assert ordered(siblings) == names
