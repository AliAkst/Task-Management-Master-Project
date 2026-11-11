"""Faz 8a: checklist + etiket araclari, create_card genislemesi, "bu kart" baglami."""

import json
from zoneinfo import ZoneInfo

import pytest
from httpx import ASGITransport, AsyncClient

import app.api.chat as chat_module
from app.agent.actions import ActionGate
from app.api.deps import current_user
from app.main import app
from app.tools.privacy import PrivacyFilter
from app.tools.read_tools import ToolBox
from app.tools.task_api import TaskApiClient
from app.tools.write_tools import ACTION_TYPES, WriteTools
from tests.conftest import CARDS, FakeProvider, _card, call, text
from tests.test_chat_api import USER, parse_sse

TZ = ZoneInfo("Europe/Istanbul")
ACIL = {"id": 31, "board_id": 1, "name": "Acil", "color": "#ef4444"}
BEKLIYOR = {"id": 32, "board_id": 1, "name": "Bekliyor", "color": "#eab308"}


def checklist(*texts: str, done: tuple[int, ...] = ()) -> list[dict]:
    return [
        {"id": 60 + i, "text": t, "is_done": (60 + i) in done}
        for i, t in enumerate(texts)
    ]


@pytest.fixture
def api(fake_api):
    fake_api.board_labels[1] = [dict(ACIL), dict(BEKLIYOR)]
    fake_api.card_extra[11] = {
        "checklist": checklist("Giriş", "Kaynakça"),
        "label_ids": [32],
    }
    return fake_api


def writer(transport, cloud=False):
    privacy = PrivacyFilter(
        active=cloud,
        hidden_boards={2} if cloud else set(),
        hidden_cards={21} if cloud else set(),
    )
    return WriteTools(TaskApiClient("t", transport=transport), privacy, TZ)


# ---------------- hazirlik: checklist ----------------
class TestChecklistPrepare:
    async def test_add_summary_and_dedupe(self, api, task_api_transport):
        p = await writer(task_api_transport).prepare(
            "add_checklist_items",
            {"card_id": 11, "items": ["Özet", "giriş", " Sonuç ", "Özet", ""]},
        )
        assert p.action_type == "edit_checklist"
        assert p.args == {"card_id": 11, "add": ["Özet", "Sonuç"], "changes": []}
        assert p.summary.startswith("☑️ 'Koşu' kartına 2 madde: «Özet», «Sonuç»")
        assert "zaten var: giriş" in p.summary

    async def test_add_all_duplicates_rejected(self, api, task_api_transport):
        with pytest.raises(ValueError, match="zaten var"):
            await writer(task_api_transport).prepare(
                "add_checklist_items", {"card_id": 11, "items": ["giriş"]}
            )

    async def test_item_limits(self, api, task_api_transport):
        w = writer(task_api_transport)
        ok = await w.prepare(
            "add_checklist_items", {"card_id": 11, "items": [f"m{i}" for i in range(20)]}
        )
        assert len(ok.args["add"]) == 20
        with pytest.raises(ValueError, match="en fazla 20"):
            await w.prepare(
                "add_checklist_items",
                {"card_id": 11, "items": [f"m{i}" for i in range(21)]},
            )
        long = await w.prepare(
            "add_checklist_items", {"card_id": 11, "items": ["x" * 900]}
        )
        assert len(long.args["add"][0]) == 500

    async def test_update_summary(self, api, task_api_transport):
        p = await writer(task_api_transport).prepare(
            "update_checklist_items",
            {"card_id": 11, "changes": [{"item_id": 61, "is_done": True}]},
        )
        assert p.action_type == "edit_checklist"
        assert p.summary == "☑️ 'Koşu': «Kaynakça» ✓ tamamlandı"
        assert p.args["changes"] == [{"item_id": 61, "is_done": True}]

    async def test_item_of_another_card_rejected(self, api, task_api_transport):
        api.card_extra[21] = {"checklist": checklist("Gizli madde")}
        api.card_extra[21]["checklist"][0]["id"] = 99
        w = writer(task_api_transport)
        for name, args in [
            ("update_checklist_items", {"card_id": 11, "changes": [{"item_id": 99, "is_done": True}]}),
            ("delete_checklist_items", {"card_id": 11, "item_ids": [99]}),
        ]:
            with pytest.raises(ValueError, match="kartta yok"):
                await w.prepare(name, args)

    async def test_delete_summary_lists_names(self, api, task_api_transport):
        p = await writer(task_api_transport).prepare(
            "delete_checklist_items", {"card_id": 11, "item_ids": [60, 61]}
        )
        assert p.action_type == "delete_checklist_items"
        assert "2 madde silinir" in p.summary
        assert "- Giriş" in p.summary and "- Kaynakça" in p.summary


# ---------------- hazirlik: etiket ----------------
class TestLabelPrepare:
    async def test_turkish_dotted_capital_i_matches(self, api, task_api_transport):
        p = await writer(task_api_transport).prepare(
            "set_card_labels",
            {"card_id": 11, "add": ["ACİL!", "Okul"], "remove": ["bekliyor"]},
        )
        assert p.action_type == "manage_labels"
        # "ACİL!" -> casefold sonrasi birlesik nokta atilir -> "acil" ile eslesir
        assert p.args["add_ids"] == [31]
        assert p.args["add_new"] == ["Okul"]

    async def test_existing_label_matches_ignoring_case_and_punctuation(
        self, api, task_api_transport
    ):
        p = await writer(task_api_transport).prepare(
            "set_card_labels",
            {"card_id": 11, "add": ["acil!", "Okul"], "remove": ["Bekliyor", "Yok"]},
        )
        assert p.args["add_ids"] == [31]
        assert p.args["add_new"] == ["Okul"]
        assert p.args["remove_ids"] == [32]
        assert p.summary == (
            "🏷 'Koşu': +Acil, +Okul (yeni etiket; mevcutlar: Acil, Bekliyor), "
            "−Bekliyor (yok sayıldı: Yok etiketi board'da yok)"
        )

    async def test_noop_rejected(self, api, task_api_transport):
        with pytest.raises(ValueError, match="Değişiklik yok"):
            await writer(task_api_transport).prepare(
                "set_card_labels", {"card_id": 11, "add": ["Bekliyor"]}
            )
        with pytest.raises(ValueError, match="en az bir etiket"):
            await writer(task_api_transport).prepare("set_card_labels", {"card_id": 11})

    async def test_create_card_with_labels_and_checklist(
        self, api, task_api_transport
    ):
        p = await writer(task_api_transport).prepare(
            "create_card",
            {
                "board_id": 1,
                "title": "Tez",
                "labels": ["Acil", "Okul"],
                "checklist": ["Özet", "Giriş"],
            },
        )
        assert p.args["_labels"] == {
            "board_id": 1,
            "add_ids": [31],
            "add_new": ["Okul"],
        }
        assert p.args["_checklist"] == ["Özet", "Giriş"]
        assert "\n🏷 +Acil, +Okul (yeni etiket" in p.summary
        assert "\n☑️ 2 madde: «Özet», «Giriş»" in p.summary

    async def test_hidden_board_refused_for_cloud_model(self, api, task_api_transport):
        w = writer(task_api_transport, cloud=True)
        for name, args in [
            ("add_checklist_items", {"card_id": 21, "items": ["x"]}),
            ("set_card_labels", {"card_id": 21, "add": ["x"]}),
            ("create_card", {"board_id": 2, "title": "x", "labels": ["a"]}),
        ]:
            with pytest.raises(ValueError, match="gizli"):
                await w.prepare(name, args)


# ---------------- yurutme ----------------
class TestExecute:
    async def test_checklist_add_and_update_as_ai(self, api, task_api_transport):
        w = writer(task_api_transport)
        r = await w.execute(
            "edit_checklist",
            {
                "card_id": 11,
                "add": ["Özet"],
                "changes": [{"item_id": 61, "is_done": True}],
            },
        )
        assert r["added"] == 1 and r["updated"] == 1 and r["skipped"] == []
        assert all(x["actor"] == "ai" for x in api.writes)
        assert api.card_extra[11]["checklist"][1]["is_done"] is True

    async def test_update_and_delete_skip_missing_items(self, api, task_api_transport):
        w = writer(task_api_transport)
        r = await w.execute(
            "edit_checklist",
            {"card_id": 11, "changes": [{"item_id": 999, "is_done": True}]},
        )
        assert r["skipped"] == [999] and r["updated"] == 0
        r = await w.execute(
            "delete_checklist_items", {"card_id": 11, "item_ids": [60, 999]}
        )
        assert r["deleted"] == [60] and r["skipped"] == [999]
        assert [i["text"] for i in api.card_extra[11]["checklist"]] == ["Kaynakça"]

    async def test_labels_merge_with_changes_made_after_proposal(
        self, api, task_api_transport
    ):
        w = writer(task_api_transport)
        p = await w.prepare("set_card_labels", {"card_id": 11, "add": ["Acil"]})
        # Oneri ile onay arasinda kullanici kartta baska bir etiket tutmus
        extra = {"id": 33, "board_id": 1, "name": "Okul", "color": "#000"}
        api.board_labels[1].append(extra)
        api.card_extra[11]["label_ids"] = [32, 33]
        await w.execute(p.action_type, p.args)
        patch = [x for x in api.writes if x["method"] == "PATCH"][-1]
        assert patch["path"] == "/cards/11"
        assert patch["body"]["label_ids"] == [32, 33, 31]  # 33 kaybolmadi

    async def test_missing_label_is_created_then_attached(self, api, task_api_transport):
        w = writer(task_api_transport)
        p = await w.prepare(
            "set_card_labels", {"card_id": 11, "add": ["Okul"], "remove": ["Bekliyor"]}
        )
        await w.execute(p.action_type, p.args)
        created = [x for x in api.writes if x["path"] == "/boards/1/labels"]
        assert len(created) == 1 and created[0]["body"] == {"name": "Okul"}
        new_id = api.board_labels[1][-1]["id"]
        assert api.card_extra[11]["label_ids"] == [new_id]

    async def test_label_created_meanwhile_is_reused(self, api, task_api_transport):
        w = writer(task_api_transport)
        p = await w.prepare("set_card_labels", {"card_id": 11, "add": ["Okul"]})
        api.board_labels[1].append(
            {"id": 77, "board_id": 1, "name": "okul", "color": "#000"}
        )
        await w.execute(p.action_type, p.args)
        assert not [x for x in api.writes if x["path"] == "/boards/1/labels"]
        assert 77 in api.card_extra[11]["label_ids"]

    async def test_create_card_with_labels_and_checklist(
        self, api, task_api_transport, monkeypatch
    ):
        monkeypatch.setitem(CARDS, 100, _card(100, "Tez", 1))
        w = writer(task_api_transport)
        p = await w.prepare(
            "create_card",
            {
                "board_id": 1,
                "title": "Tez",
                "force_new": True,
                "labels": ["Acil", "Okul"],
                "checklist": ["Özet", "Giriş"],
            },
        )
        r = await w.execute(p.action_type, p.args)
        assert r["card_id"] == 100 and "note" not in r
        post = next(x for x in api.writes if x["path"] == "/cards")
        assert post["body"] == {"list_id": 10, "title": "Tez"}  # _ anahtarlari gitmez
        assert len(api.card_extra[100]["label_ids"]) == 2
        assert [i["text"] for i in api.card_extra[100]["checklist"]] == ["Özet", "Giriş"]

    async def test_card_survives_extra_step_failure(
        self, api, task_api_transport, monkeypatch
    ):
        monkeypatch.setitem(CARDS, 100, _card(100, "Tez", 1))
        api.fail_paths.add("/cards/100/checklist")
        w = writer(task_api_transport)
        p = await w.prepare(
            "create_card",
            {"board_id": 1, "title": "Tez", "checklist": ["Özet"], "force_new": True},
        )
        r = await w.execute(p.action_type, p.args)
        assert r["card_id"] == 100
        assert r["note"].startswith("Kart oluşturuldu; checklist eklenemedi")


# ---------------- izinler ----------------
class TestPermissions:
    async def make_box(self, transport, db_session_maker, modes):
        box = await ToolBox.create(
            TaskApiClient("t", transport=transport), cloud=False, tz=TZ
        )
        box.gate = ActionGate(
            db_session_maker,
            box.writer,
            user_id=7,
            conversation_id=None,
            model_id="m",
            modes=modes,
        )
        return box

    def test_three_new_types_are_listed_for_settings_ui(self):
        assert ACTION_TYPES["edit_checklist"] == "Checklist düzenleme"
        assert ACTION_TYPES["manage_labels"] == "Etiket ekleme/çıkarma"
        assert ACTION_TYPES["delete_checklist_items"] == "Checklist maddesi silme"

    async def test_never_hides_tools_ask_proposes_auto_runs(
        self, api, task_api_transport, db_session_maker
    ):
        box = await self.make_box(
            task_api_transport,
            db_session_maker,
            {"edit_checklist": "never", "manage_labels": "ask"},
        )
        names = {s.name for s in box.specs()}
        assert "add_checklist_items" not in names
        assert "update_checklist_items" not in names
        assert "set_card_labels" in names and "delete_checklist_items" in names
        r = await box.execute(
            call("add_checklist_items", card_id=11, items=["x"]).tool_call
        )
        assert r.ok is False

        r = await box.execute(
            call("set_card_labels", card_id=11, add=["Acil"]).tool_call
        )
        assert json.loads(r.text)["status"] == "pending_approval"
        assert not [x for x in api.writes if x["method"] == "PATCH"]

        box.gate.modes["manage_labels"] = "auto"
        r = await box.execute(
            call("set_card_labels", card_id=11, add=["Acil"]).tool_call
        )
        assert json.loads(r.text)["status"] == "done"
        assert api.card_extra[11]["label_ids"] == [32, 31]


# ---------------- okuma ----------------
class TestReadTools:
    async def test_get_card_returns_ids_and_labels(self, api, task_api_transport):
        box = await ToolBox.create(
            TaskApiClient("t", transport=task_api_transport), cloud=False, tz=TZ
        )
        out = await box.get_card(11)
        assert out["checklist_items"] == [
            {"id": 60, "text": "Giriş", "is_done": False},
            {"id": 61, "text": "Kaynakça", "is_done": False},
        ]
        assert out["labels"] == [{"id": 32, "name": "Bekliyor"}]

    async def test_get_card_lists_attachment_names_only(
        self, api, task_api_transport
    ):
        api.card_extra[11]["attachments"] = [
            {"id": 5, "filename": "rapor.pdf", "url": "/x?token=gizli", "size_bytes": 9}
        ]
        box = await ToolBox.create(
            TaskApiClient("t", transport=task_api_transport), cloud=False, tz=TZ
        )
        out = await box.get_card(11)
        assert out["attachments"] == ["rapor.pdf"]
        assert "token" not in json.dumps(out)

    async def test_get_board_lists_labels(self, api, task_api_transport):
        box = await ToolBox.create(
            TaskApiClient("t", transport=task_api_transport), cloud=False, tz=TZ
        )
        out = await box.get_board(1)
        assert out["labels"] == ["Acil", "Bekliyor"]
        assert out["cards"][0]["labels"] == ["Bekliyor"]


# ---------------- "bu kart" baglami ----------------
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
        yield c
    app.dependency_overrides.clear()


async def ask(client, model_id, **extra):
    res = await client.post(
        "/api/v1/assistant/chat",
        json={"message": "bu karta madde ekle", "model_id": model_id, **extra},
    )
    assert res.status_code == 200, res.text
    return parse_sse(res.text)


class TestFocusContext:
    async def test_card_context_in_system_prompt(self, client):
        client.providers["fake:local"] = FakeProvider([[text("tamam")]])
        await ask(client, "fake:local", board_id=1, card_id=11)
        system = client.providers["fake:local"].received[0][0].content
        assert "#11 «Koşu»" in system and "«Spor»" in system
        assert "'bu kart' dediğinde" in system

    async def test_board_only_context(self, client):
        client.providers["fake:local"] = FakeProvider([[text("tamam")]])
        await ask(client, "fake:local", board_id=1)
        system = client.providers["fake:local"].received[0][0].content
        assert "«Spor» board'unda" in system and "'bu board'" in system

    async def test_no_context_without_ids(self, client):
        client.providers["fake:local"] = FakeProvider([[text("tamam")]])
        await ask(client, "fake:local")
        system = client.providers["fake:local"].received[0][0].content
        assert "'bu kart' dediğinde" not in system

    async def test_local_only_context_hidden_from_cloud_model(self, client):
        client.providers["fake:cloud"] = FakeProvider([[text("tamam")]], is_local=False)
        await ask(client, "fake:cloud", board_id=2, card_id=21)
        system = client.providers["fake:cloud"].received[0][0].content
        assert "Gizli date planı" not in system
        assert "'bu kart' dediğinde" not in system
        assert "'bu board'" not in system

    async def test_local_only_context_visible_to_local_model(self, client):
        client.providers["fake:local"] = FakeProvider([[text("tamam")]])
        await ask(client, "fake:local", board_id=2, card_id=21)
        system = client.providers["fake:local"].received[0][0].content
        assert "#21 «Gizli date planı»" in system


# ---------------- arsivli gizli board (denetim bulgusu 4) ----------------
class TestArchivedLocalOnly:
    async def test_archived_local_only_board_hidden_from_cloud(self):
        import httpx

        def handler(request: httpx.Request) -> httpx.Response:
            path = request.url.path.removeprefix("/api/v1")
            archived = request.url.params.get("include_archived") == "true"
            if path == "/boards":
                boards = [{"id": 9, "name": "Eski", "privacy": "local_only"}] if archived else []
                return httpx.Response(200, json={"success": True, "data": boards})
            if path == "/boards/9":
                return httpx.Response(
                    200, json={"success": True, "data": {"cards": [{"id": 90}]}}
                )
            return httpx.Response(404, json={"success": False})

        box = await ToolBox.create(
            TaskApiClient("t", transport=httpx.MockTransport(handler)), cloud=True, tz=TZ
        )
        assert box.privacy.board_hidden(9)
        assert box.privacy.card_hidden(90)
