"""Faz 5b: kullanici hafizasi (bilgiler), hedefler, tanisma, profil API'si."""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

import app.api.chat as chat_module
from app.api.deps import current_user
from app.db.models import UserFactEntity
from app.main import app
from app.tools.task_api import TaskApiClient
from tests.conftest import FakeProvider, call, text
from tests.test_chat_api import USER, parse_sse

API = "/api/v1/assistant"


@pytest.fixture
async def client(monkeypatch, db_session_maker, task_api_transport):
    providers: dict[str, FakeProvider] = {}
    monkeypatch.setattr(
        chat_module, "build_provider", lambda mid, cloud=None: providers[mid]
    )
    monkeypatch.setattr(chat_module, "session_maker", db_session_maker)
    monkeypatch.setattr(
        chat_module,
        "TaskApiClient",
        lambda token: TaskApiClient(token, transport=task_api_transport),
    )

    async def fake_session():
        async with db_session_maker() as s:
            yield s

    app.dependency_overrides[current_user] = lambda: USER
    app.dependency_overrides[chat_module.get_session] = fake_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        c.providers = providers  # type: ignore[attr-defined]
        c.db = db_session_maker  # type: ignore[attr-defined]
        yield c
    app.dependency_overrides.clear()


async def chat(client, message, model="fake:local", conversation_id=None):
    res = await client.post(
        f"{API}/chat",
        json={
            "message": message,
            "model_id": model,
            "conversation_id": conversation_id,
        },
    )
    return parse_sse(res.text)


def system_prompt(provider: FakeProvider, turn: int = -1) -> str:
    return provider.received[turn][0].content


async def test_new_user_gets_acquaintance_instruction(client):
    client.providers["fake:local"] = FakeProvider([[text("Merhaba! Seni tanıyalım.")]])
    await chat(client, "Selam")
    prompt = system_prompt(client.providers["fake:local"])
    assert "henüz yeterince tanımıyorsun" in prompt and "TEK soru" in prompt


async def test_remember_fact_approval_then_in_context(client):
    client.providers["fake:local"] = FakeProvider(
        [
            [
                call(
                    "remember_fact",
                    category="routine",
                    content="Sabahları 7'de kalkıyor",
                )
            ],
            [text("Bunu hatırlamayı önerdim.")],
            [text("Tamam.")],
        ]
    )
    events = await chat(client, "Ben hep 7'de kalkarım")
    action = next(d for e, d in events if e == "action")
    assert action["status"] == "proposed" and "Rutinler" in action["summary"]

    res = await client.post(f"{API}/actions/{action['id']}/approve", json={})
    assert res.json()["data"]["status"] == "executed"

    facts = (await client.get(f"{API}/facts")).json()["data"]["facts"]
    assert [(f["content"], f["source"]) for f in facts] == [
        ("Sabahları 7'de kalkıyor", "ai_learned")
    ]

    await chat(client, "Yarın ne yapayım?")
    assert f"[{facts[0]['id']}, routine] Sabahları 7'de kalkıyor" in system_prompt(
        client.providers["fake:local"]
    )


async def test_private_facts_never_reach_cloud(client):
    await client.post(
        f"{API}/facts", json={"category": "health", "content": "Dizinde sakatlık var"}
    )
    await client.post(
        f"{API}/facts", json={"category": "work", "content": "Backend geliştirici"}
    )
    facts = (await client.get(f"{API}/facts")).json()["data"]["facts"]
    private = next(f for f in facts if f["category"] == "health")
    assert private["is_private"] is True  # saglik varsayilan olarak gizli

    cloud = FakeProvider(
        [[call("forget_fact", fact_id=private["id"])], [text("ok")]], is_local=False
    )
    client.providers["fake:cloud"] = cloud
    events = await chat(client, "Beni tanıyor musun?", model="fake:cloud")
    sent = cloud.all_text_sent()
    assert "Backend geliştirici" in sent
    assert "sakatlık" not in sent
    # Bulut model gizli bilgiyi silmeye calisirsa reddedilir (oneri bile olusmaz)
    assert not any(e == "action" for e, _ in events)


async def test_save_goal_goes_to_task_api_as_ai(client, fake_api):
    client.providers["fake:local"] = FakeProvider(
        [
            [
                call(
                    "save_goal",
                    title="Docker sertifikası",
                    why="Kariyer",
                    target_date="2027-03-01",
                    board_id=1,
                )
            ],
            [text("Hedefi önerdim.")],
            [text("ok")],
        ]
    )
    events = await chat(client, "Mart'a kadar Docker sertifikası almak istiyorum")
    action = next(d for e, d in events if e == "action")
    assert action["action_type"] == "manage_goal"
    assert action["summary"].startswith(
        "🎯 Yeni hedef: 'Docker sertifikası' (hedef tarih Pzt 1 Mar, Spor)"
    )
    await client.post(f"{API}/actions/{action['id']}/approve", json={})
    write = fake_api.writes[-1]
    assert (write["method"], write["path"], write["actor"]) == ("POST", "/goals", "ai")

    # Aktif hedef bir sonraki turda sistem mesajinda
    await chat(client, "Bu hafta ne yapayım?")
    assert "[hedef 1] Docker sertifikası" in system_prompt(
        client.providers["fake:local"]
    )


async def test_never_manage_goal_hides_save_goal(client):
    await client.put(f"{API}/permissions/manage_goal", json={"mode": "never"})
    provider = FakeProvider([[text("ok")]])
    client.providers["fake:local"] = provider
    await chat(client, "x")
    # FakeProvider arac listesini kaydeder
    tools = {t.name for t in provider.tools_seen[0]}
    assert "save_goal" not in tools
    # Hafiza bilgileri sohbet modeline hic gosterilmez (ayri hafiza adimi kullanir)
    assert "remember_fact" not in tools and "forget_fact" not in tools
    assert "schedule_day" in tools


async def test_facts_api_crud_and_ownership(client):
    res = await client.post(f"{API}/facts", json={"category": "yok", "content": "x"})
    assert res.status_code == 422
    f = (
        await client.post(
            f"{API}/facts", json={"category": "preference", "content": "Kahve sever"}
        )
    ).json()["data"]
    assert f["is_private"] is False and f["source"] == "user_entered"

    res = await client.patch(
        f"{API}/facts/{f['id']}", json={"content": "Çay sever", "is_private": True}
    )
    assert (
        res.json()["data"]["content"] == "Çay sever"
        and res.json()["data"]["is_private"] is True
    )

    app.dependency_overrides[current_user] = lambda: {**USER, "id": 99}
    assert (await client.get(f"{API}/facts")).json()["data"]["facts"] == []
    assert (
        await client.patch(f"{API}/facts/{f['id']}", json={"content": "y"})
    ).status_code == 404
    assert (await client.delete(f"{API}/facts/{f['id']}")).status_code == 404

    app.dependency_overrides[current_user] = lambda: USER
    assert (await client.delete(f"{API}/facts/{f['id']}")).status_code == 204
    async with client.db() as s:  # type: ignore[attr-defined]
        assert (await s.scalars(select(UserFactEntity))).all() == []


@pytest.fixture
def extraction_on(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "memory_extraction", True)


async def test_extractor_proposes_fact_when_chat_model_does_not(client, extraction_on):
    provider = FakeProvider(
        [
            [text("Harika, peki hafta sonları ne yaparsın?")],  # sohbet: arac yok
            [
                call(
                    "remember_fact",
                    category="routine",
                    content="Akşam 20-22 arası en verimli saatleri",
                )
            ],
        ]
    )
    client.providers["fake:local"] = provider
    events = await chat(client, "En verimli olduğum saatler akşam 20 ile 22 arası")
    action = next(d for e, d in events if e == "action")
    assert action["action_type"] == "remember_fact" and "20-22" in action["summary"]
    # Cikarim istemi odakli: sadece hafiza araclari + bilinen bilgiler listesi
    assert {t.name for t in provider.tools_seen[1]} == {"remember_fact", "save_goal"}
    assert "Bilinen bilgiler" in provider.received[1][0].content
    # Sohbet modeline "not aldım deme" talimati
    assert "DEME" in provider.received[0][0].content


async def test_extractor_skips_short_messages_and_when_chat_used_memory(
    client, extraction_on
):
    provider = FakeProvider([[text("Selam!")]])
    client.providers["fake:local"] = provider
    await chat(client, "Selam")
    assert len(provider.received) == 1  # kisa mesaj: cikarim yok

    provider = FakeProvider(
        [
            [call("remember_fact", category="work", content="Backend geliştirici")],
            [text("ok")],
        ]
    )
    client.providers["fake:local"] = provider
    await chat(client, "Ben backend geliştiricisiyim, uzun zamandır")
    assert len(provider.received) == 2  # sohbet zaten kaydetti: cikarim calismadi


async def test_extracted_proposals_survive_history_reload(client, extraction_on):
    client.providers["fake:local"] = FakeProvider(
        [
            [text("Güzel.")],
            [call("remember_fact", category="work", content="Backend geliştirici")],
        ]
    )
    events = await chat(client, "Ben backend geliştiricisiyim")
    conv = events[0][1]["conversation_id"]
    msgs = (await client.get(f"{API}/conversations/{conv}/messages")).json()["data"]
    answer = next(m for m in msgs if m["role"] == "assistant")
    assert [a["action_type"] for a in answer["actions"]] == ["remember_fact"]


async def test_duplicate_fact_is_not_proposed_again(client):
    await client.post(
        f"{API}/facts", json={"category": "routine", "content": "Sabah koşar"}
    )
    from app.tools.memory_tools import MemoryTools

    tools = MemoryTools(client.db, USER["id"], cloud=False)
    with pytest.raises(ValueError, match="zaten kayıtlı"):
        await tools.prepare_remember("sabah koşar", "routine")


async def test_no_memory_extraction_after_action_turn(client, extraction_on):
    """Komut turunda (kart/plan onerisi) mesaj kisisel bilgi sayilmaz."""
    provider = FakeProvider(
        [
            [call("create_card", board_id=1, title="Kuyumcu")],
            [text("Önerdim.")],
            [
                call(
                    "remember_fact",
                    content="Salı kuyumcuya gidiyor",
                    category="routine",
                )
            ],
        ]
    )
    client.providers["fake:local"] = provider
    events = await chat(client, "Salı iş çıkışı kuyumcuya uğramam lazım, kart aç")
    kinds = [d["action_type"] for e, d in events if e == "action"]
    assert kinds == ["create_card"]
    assert len(provider.received) == 2  # hafiza cagrisi yapilmadi


async def test_deleting_conversation_detaches_its_actions(client):
    from app.db.models import AiActionEntity

    client.providers["fake:local"] = FakeProvider(
        [[call("create_card", board_id=1, title="X")], [text("ok")]]
    )
    events = await chat(client, "kart aç")
    conv = next(d for e, d in events if e == "start")["conversation_id"]
    await client.delete(f"{API}/conversations/{conv}")
    async with client.db() as s:
        action = await s.scalar(select(AiActionEntity))
    assert action.conversation_id is None  # yeni sohbete karismaz


async def test_tidy_profile_on_request(client):
    """'Profilimi temizle' -> kod tekrarlari/tek gune ait/anlamsizlari bulur, onayla gider."""
    for content in (
        "Haftada 3 gün sabah koşuyor",
        "Haftada 3 gün sabah koşuyor.",
        "Salı günü kuyumcuya uğruyor.",
        "Kullanıcı eklememiş.",
        "İşe 9'da başlıyor",
    ):
        await client.post(
            f"{API}/facts", json={"category": "routine", "content": content}
        )
    client.providers["fake:local"] = FakeProvider([])  # model hic cagrilmaz
    events = await chat(client, "Profilimi temizler misin, çok tekrar var")
    action = next(d for e, d in events if e == "action")
    assert action["action_type"] == "forget_fact"
    assert "3 bilgi kaldırılır, 2 bilgi kalır" in action["summary"]
    assert client.providers["fake:local"].received == []

    res = await client.post(f"{API}/actions/{action['id']}/approve", json={})
    assert res.json()["data"]["status"] == "executed"
    facts = (await client.get(f"{API}/facts")).json()["data"]["facts"]
    assert sorted(f["content"] for f in facts) == [
        "Haftada 3 gün sabah koşuyor",
        "İşe 9'da başlıyor",
    ]


# ============ Faz 13h2: yakin tekrar, birlestirme, kalici silme ============
import json  # noqa: E402
from datetime import UTC, datetime, timedelta  # noqa: E402
from zoneinfo import ZoneInfo  # noqa: E402

from app.agent.actions import ActionGate  # noqa: E402
from app.llm.types import ToolCall  # noqa: E402
from app.tools.memory_tools import MemoryTools, purge_inactive  # noqa: E402
from app.tools.privacy import PrivacyFilter  # noqa: E402
from app.tools.task_api import TaskApiError  # noqa: E402
from app.tools.write_tools import WriteTools  # noqa: E402

NOW = datetime(2026, 11, 14, 12, 0, tzinfo=UTC)

# G2: 8 kayitlik uydurma kume (13h2 oncesi kodla kaydedilen ciktilar)
G2_SET = [
    ("routine", "Haftada 3 gün sabah koşuyor"),
    ("routine", "Haftada 3 gün sabah koşuyor."),
    ("routine", "Salı günü kuyumcuya uğruyor."),
    ("other", "Kullanıcı eklememiş."),
    ("work", "İşe 9'da başlıyor"),
    ("preference", "Kahveyi şekersiz içer"),
    ("health", "Dizinde ağrı var"),
    ("personal", "Ankara'da yaşıyor"),
]


class StubApi:
    def __init__(self, templates=None, fail=False):
        self.templates = templates or []
        self.fail = fail
        self.calls = 0

    async def get(self, path, **_):
        self.calls += 1
        assert path == "/day-templates"
        if self.fail:
            raise TaskApiError(500, "x")
        return self.templates


async def add_facts(maker, rows, user_id=7, *, active=True, updated_at=None):
    ids = []
    async with maker() as s:
        for cat, content in rows:
            f = UserFactEntity(
                user_id=user_id,
                category=cat,
                content=content,
                is_active=active,
                is_private=cat in ("health", "relationship"),
            )
            if updated_at:
                f.updated_at = updated_at
            s.add(f)
            await s.flush()
            ids.append(f.id)
        await s.commit()
    return ids


async def test_g2_old_tidy_and_remember_outputs_unchanged(db_session_maker):
    await add_facts(db_session_maker, G2_SET)
    m = MemoryTools(db_session_maker, 7, cloud=False, api=StubApi())
    body, summary = await m.prepare_tidy()
    assert body == {"fact_ids": [2, 3, 4]}
    assert summary == (
        "🧹 Profil temizliği: 3 bilgi kaldırılır, 5 bilgi kalır\n"
        "- «Haftada 3 gün sabah koşuyor.» (tekrar)\n"
        "- «Salı günü kuyumcuya uğruyor.» (tek güne ait)\n"
        "- «Kullanıcı eklememiş.» (anlamsız)"
    )
    with pytest.raises(ValueError, match="zaten kayıtlı"):
        await m.prepare_remember("Haftada 3 gün sabah koşuyor")
    assert await m.prepare_remember("Yeni bir bilgi", "work") == (
        {"content": "Yeni bir bilgi", "category": "work", "is_private": False},
        "🧠 Hatırlanacak (İş ve kariyer): «Yeni bir bilgi»",
    )
    assert await m.prepare_remember("Güncel", fact_id=5) == (
        {"fact_id": 5, "content": "Güncel", "category": "work"},
        "🧠 Bilgi güncellenir: «İşe 9'da başlıyor» → «Güncel»",
    )


TEMPLATE_FACT = "Evden çalışınca 09:00-18:00 mesai, 12:00-13:00 öğle"


async def test_template_rule_needs_a_template(db_session_maker):
    await add_facts(
        db_session_maker,
        [("routine", TEMPLATE_FACT), ("work", "Ofiste 8-17 çalışır")],
    )
    # sablon yok -> kural calismaz
    m = MemoryTools(db_session_maker, 7, cloud=False, api=StubApi([]))
    with pytest.raises(ValueError, match="Temizlenecek bilgi yok"):
        await m.prepare_tidy()
    # api hatasi -> kural calismaz, tidy dusmez
    m = MemoryTools(db_session_maker, 7, cloud=False, api=StubApi(fail=True))
    with pytest.raises(ValueError, match="Temizlenecek bilgi yok"):
        await m.prepare_tidy()
    # sablon var -> iki kayit da "Gün şablonunda var"
    m = MemoryTools(db_session_maker, 7, cloud=False, api=StubApi([{"id": 1}]))
    body, summary = await m.prepare_tidy()
    assert body["forget_ids"] == [1, 2] and body["merges"] == []
    assert "Hafıza düzenleme: 2 bilgi kaldırılacak, 0 çift birleştirilecek" in summary
    assert "(Gün şablonunda var)" in summary


async def test_template_rule_negatives(db_session_maker):
    """Tek saat / kategori uyumsuz / ipucu yok -> sablon kurali yakalamaz."""
    await add_facts(
        db_session_maker,
        [
            ("routine", "Ofiste 9'da başlar"),
            ("preference", "Mesai 09:00-18:00 olsun"),
            ("routine", "Spor 07:00-08:00 arası"),
        ],
    )
    api = StubApi([{"id": 1}])
    m = MemoryTools(db_session_maker, 7, cloud=False, api=api)
    with pytest.raises(ValueError, match="Temizlenecek bilgi yok"):
        await m.prepare_tidy()
    assert api.calls == 0  # aday yoksa task-api'ye gidilmez


async def test_merge_proposal_with_local_model_sentence(db_session_maker):
    ids = await add_facts(
        db_session_maker,
        [
            ("routine", "Spor salonuna haftada 3 gün gider"),
            ("routine", "Haftada 3 gün spor salonuna gidiyor"),
            ("preference", "Kahveyi şekersiz içer"),
        ],
    )
    prov = FakeProvider([[text("Haftada 3 gün spor salonuna gider.")]])
    m = MemoryTools(db_session_maker, 7, cloud=False, api=StubApi(), provider=prov)
    body, summary = await m.prepare_tidy()
    assert body == {
        "forget_ids": [],
        "merges": [{"ids": ids[:2], "content": "Haftada 3 gün spor salonuna gider."}],
    }
    assert "0 bilgi kaldırılacak, 1 çift birleştirilecek" in summary
    assert "⇄ «Spor salonuna haftada 3 gün gider» + «Haftada 3 gün spor" in summary
    assert "TEK kısa Türkçe cümlede birleştir" in prov.received[0][0].content
    assert len(prov.received) == 1


@pytest.mark.parametrize("reply", ["", "x" * 201, "Birinci satır\nİkinci satır"])
async def test_merge_sentence_falls_back_to_newest(db_session_maker, reply):
    old = datetime(2026, 1, 1, tzinfo=UTC)
    await add_facts(
        db_session_maker, [("routine", "Haftada iki gün ofiste")], updated_at=old
    )
    await add_facts(db_session_maker, [("routine", "Haftada iki gün ofiste çalışır")])
    prov = FakeProvider([[text(reply)]] if reply else [[]])
    m = MemoryTools(db_session_maker, 7, cloud=False, provider=prov)
    body, _ = await m.prepare_tidy()
    assert body["merges"][0]["content"] == "Haftada iki gün ofiste çalışır"


async def test_merge_sentence_model_error_falls_back(db_session_maker):
    await add_facts(db_session_maker, [("routine", "Haftada iki gün ofiste")])
    await add_facts(db_session_maker, [("routine", "Haftada iki gün ofiste çalışır")])

    class Boom:
        info = FakeProvider([]).info

        async def stream(self, *a, **k):
            raise RuntimeError("model yok")
            yield

    m = MemoryTools(db_session_maker, 7, cloud=False, provider=Boom())
    body, _ = await m.prepare_tidy()
    assert body["merges"][0]["content"] == "Haftada iki gün ofiste çalışır"


async def test_cloud_mode_never_calls_model_for_merge(db_session_maker):
    await add_facts(db_session_maker, [("routine", "Haftada iki gün ofiste")])
    await add_facts(db_session_maker, [("routine", "Haftada iki gün ofiste çalışır")])
    prov = FakeProvider([[text("MODEL CAGRILDI")]], is_local=False)
    m = MemoryTools(db_session_maker, 7, cloud=True, provider=prov)
    body, _ = await m.prepare_tidy()
    assert prov.received == []  # sayac: hic cagri yok
    assert body["merges"][0]["content"] == "Haftada iki gün ofiste çalışır"
    # bulut + gizli kayit: ikisi de gorunmez -> eslesme eklenmez
    await add_facts(db_session_maker, [("health", "Diz ağrısı için egzersiz yapar")])
    await add_facts(db_session_maker, [("health", "Diz ağrısı için egzersiz yapıyor")])
    body, _ = await m.prepare_tidy()
    assert len(body["merges"]) == 1
    assert prov.received == []


async def test_merge_at_most_five_pairs_and_each_fact_once(db_session_maker):
    rows = []
    for i in range(7):
        rows += [
            ("routine", f"Konu{i}abc haftada üç gün"),
            ("routine", f"Konu{i}abc haftada üç gün yapar"),
        ]
    rows.append(("routine", "Konu0abc haftada üç gün yapıyor"))  # 3. benzer
    await add_facts(db_session_maker, rows)
    m = MemoryTools(db_session_maker, 7, cloud=False)
    body, _ = await m.prepare_tidy()
    used = [i for mg in body["merges"] for i in mg["ids"]]
    assert len(body["merges"]) == 5 and len(used) == len(set(used)) == 10


async def test_execute_merge_creates_new_fact_and_deactivates_old(db_session_maker):
    ids = await add_facts(
        db_session_maker,
        [
            ("health", "Haftada 3 gün yüzer"),
            ("health", "Haftada üç gün yüzüyor"),
            ("routine", "Geçersiz kayıt"),
            ("routine", "Tekrar kaydı"),
        ],
    )
    m = MemoryTools(db_session_maker, 7, cloud=False)
    res = await m.execute(
        "merge_facts",
        {
            "forget_ids": [ids[2]],
            "merges": [{"ids": ids[:2], "content": "Haftada 3 gün yüzer."}],
        },
    )
    assert res["merged"] == [ids[:2]] and res["forgotten"] == [ids[2]]
    async with db_session_maker() as s:
        rows = {f.id: f for f in await s.scalars(select(UserFactEntity))}
    new = rows[res["created"][0]]
    assert (new.content, new.category, new.source) == (
        "Haftada 3 gün yüzer.",
        "health",
        "ai_learned",
    )
    assert new.is_active and new.is_private  # health -> private yayilir
    assert not rows[ids[0]].is_active and not rows[ids[1]].is_active
    assert not rows[ids[2]].is_active and rows[ids[3]].is_active


async def test_execute_merge_skips_stale_or_foreign_pairs(db_session_maker):
    mine = await add_facts(
        db_session_maker, [("routine", "Birinci kayıt"), ("routine", "İkinci kayıt")]
    )
    other = await add_facts(
        db_session_maker, [("routine", "Başkasının kaydı")], user_id=99
    )
    m = MemoryTools(db_session_maker, 7, cloud=False)
    res = await m.execute(
        "merge_facts",
        {"merges": [{"ids": [mine[0], other[0]], "content": "Sızdırma"}]},
    )
    assert res["merged"] == [] and res["created"] == []
    async with db_session_maker() as s:
        rows = {f.id: f for f in await s.scalars(select(UserFactEntity))}
    assert rows[mine[0]].is_active and rows[other[0]].is_active and len(rows) == 3
    # bir kayit arada pasiflenmisse cift atlanir, digerine dokunulmaz
    async with db_session_maker() as s:
        (await s.get(UserFactEntity, mine[1])).is_active = False
        await s.commit()
    res = await m.execute("merge_facts", {"merges": [{"ids": mine, "content": "x y"}]})
    assert res["merged"] == []
    async with db_session_maker() as s:
        assert (await s.get(UserFactEntity, mine[0])).is_active


def make_gate(maker, transport, modes):
    mem = MemoryTools(maker, 7, cloud=False)
    writer = WriteTools(
        TaskApiClient("t", transport=transport),
        PrivacyFilter(active=False),
        ZoneInfo("Europe/Istanbul"),
        memory=mem,
    )
    gate = ActionGate(
        maker, writer, user_id=7, conversation_id=None, model_id="m", modes=modes
    )
    return writer, gate


async def test_near_duplicate_remember_forces_ask_even_when_auto(
    db_session_maker, task_api_transport
):
    ids = await add_facts(
        db_session_maker, [("routine", "Spor salonuna haftada 3 gün gider")]
    )
    writer, gate = make_gate(
        db_session_maker, task_api_transport, {"remember_fact": "auto"}
    )
    prepared = await writer.prepare(
        "remember_fact",
        {"content": "Haftada 3 gün spor salonuna gidiyor", "category": "routine"},
    )
    assert prepared.force_ask is True
    assert prepared.args["fact_id"] == ids[0]
    assert prepared.summary.startswith("🧠 Bilgi güncellenir: «Spor salonuna")
    res = await gate.handle(
        ToolCall(id="c1", name="remember_fact", arguments={}), prepared
    )
    assert json.loads(res.text)["status"] == "pending_approval"
    async with db_session_maker() as s:  # onaysiz yazilmadi
        fact = await s.get(UserFactEntity, ids[0])
        assert fact.content == "Spor salonuna haftada 3 gün gider"


async def test_unrelated_remember_still_auto(db_session_maker, task_api_transport):
    await add_facts(db_session_maker, [("routine", "Spor salonuna haftada 3 gün gider")])
    writer, gate = make_gate(
        db_session_maker, task_api_transport, {"remember_fact": "auto"}
    )
    prepared = await writer.prepare(
        "remember_fact", {"content": "Kahveyi şekersiz içer", "category": "routine"}
    )
    assert prepared.force_ask is False
    res = await gate.handle(
        ToolCall(id="c2", name="remember_fact", arguments={}), prepared
    )
    assert json.loads(res.text)["status"] == "done"


async def test_merge_facts_always_asks_when_auto(db_session_maker, task_api_transport):
    await add_facts(
        db_session_maker,
        [
            ("routine", "Haftada iki gün ofiste"),
            ("routine", "Haftada iki gün ofiste çalışır"),
        ],
    )
    writer, gate = make_gate(
        db_session_maker, task_api_transport, {"merge_facts": "auto"}
    )
    prepared = await writer.prepare("tidy_facts", {})
    assert prepared.action_type == "merge_facts"
    res = await gate.handle(
        ToolCall(id="c3", name="tidy_facts", arguments={}), prepared
    )
    assert json.loads(res.text)["status"] == "pending_approval"


async def test_purge_inactive_30_day_boundary(db_session_maker):
    young = await add_facts(
        db_session_maker, [("other", "29 gün")], active=False,
        updated_at=NOW - timedelta(days=29),
    )  # fmt: skip
    old = await add_facts(
        db_session_maker, [("other", "31 gün")], active=False,
        updated_at=NOW - timedelta(days=31),
    )  # fmt: skip
    active_old = await add_facts(
        db_session_maker, [("other", "aktif eski")], updated_at=NOW - timedelta(days=90)
    )
    foreign = await add_facts(
        db_session_maker, [("other", "başkası")], user_id=99, active=False,
        updated_at=NOW - timedelta(days=90),
    )  # fmt: skip
    async with db_session_maker() as s:
        assert await purge_inactive(s, 7, NOW) == 1
    async with db_session_maker() as s:
        left = {f.id for f in await s.scalars(select(UserFactEntity))}
    assert left == {young[0], active_old[0], foreign[0]} and old[0] not in left


async def test_delete_inactive_endpoint_only_own_inactive(client):
    mine_off = await add_facts(client.db, [("other", "pasif benim")], active=False)
    mine_on = await add_facts(client.db, [("other", "aktif benim")])
    other_off = await add_facts(
        client.db, [("other", "pasif başkası")], user_id=99, active=False
    )
    got = (await client.get(f"{API}/facts")).json()["data"]
    assert got["inactive_count"] == 1 and [f["id"] for f in got["facts"]] == mine_on
    res = await client.delete(f"{API}/facts/inactive")
    assert res.status_code == 200 and res.json()["data"] == {"deleted": 1}
    async with client.db() as s:
        left = {f.id for f in await s.scalars(select(UserFactEntity))}
    assert left == {mine_on[0], other_off[0]} and mine_off[0] not in left
    assert (await client.get(f"{API}/facts")).json()["data"]["inactive_count"] == 0


async def test_chat_tidy_proposes_merge_and_approval_applies_it(client):
    ids = await add_facts(
        client.db,
        [
            ("routine", "Haftada iki gün ofiste"),
            ("routine", "Haftada iki gün ofiste çalışır"),
        ],
    )
    client.providers["fake:local"] = FakeProvider(
        [[text("Haftada iki gün ofiste çalışır.")]]
    )
    events = await chat(client, "Profilimi temizler misin")
    action = next(d for e, d in events if e == "action")
    assert action["action_type"] == "merge_facts"
    assert "1 çift birleştirilecek" in action["summary"]
    res = await client.post(f"{API}/actions/{action['id']}/approve", json={})
    assert res.json()["data"]["status"] == "executed"
    facts = (await client.get(f"{API}/facts")).json()["data"]["facts"]
    assert [f["content"] for f in facts] == ["Haftada iki gün ofiste çalışır."]
    assert all(f["id"] not in ids for f in facts)
