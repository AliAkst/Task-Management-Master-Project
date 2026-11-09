"""Faz 7a: entegrasyon altyapisi + Trello tek seferlik import (MockTransport, gercek ag yok)."""

import copy
import json
from pathlib import Path

import httpx
import pytest
from sqlalchemy import func, select

from app.core import crypto
from app.db.entities import ExternalLinkEntity, IntegrationAccountEntity, TaskEntity
from tests.integration.test_boards_cards import API

FIXTURE = json.loads(
    (Path(__file__).parent.parent / "fixtures" / "trello_board.json").read_text(
        encoding="utf-8"
    )
)
KEY, TOKEN = "trellokey12345678", "trellotoken-abcdef-1234567890"


class FakeTrello:
    """Trello API'sinin kucuk taklidi; `boards` icindeki JSON'lari dondurur."""

    def __init__(self):
        self.boards = {"board1": copy.deepcopy(FIXTURE)}
        self.requests: list[httpx.Request] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        q = request.url.params
        if q.get("key") != KEY or q.get("token") != TOKEN:
            return httpx.Response(401, text="invalid key")
        path = request.url.path
        if path == "/1/members/me":
            return httpx.Response(200, json={"fullName": "Deniz Yılmaz", "username": "ali"})
        if path == "/1/members/me/boards":
            return httpx.Response(
                200,
                json=[
                    {"id": bid, "name": b["name"], "url": b["url"], "closed": False}
                    for bid, b in self.boards.items()
                ],
            )
        bid = path.rsplit("/", 1)[-1]
        if path.startswith("/1/boards/") and bid in self.boards:
            return httpx.Response(200, json=self.boards[bid])
        return httpx.Response(404)


@pytest.fixture
def trello(monkeypatch) -> FakeTrello:
    fake = FakeTrello()
    monkeypatch.setattr(
        "app.integrations.trello.HTTP_TRANSPORT", httpx.MockTransport(fake.handler)
    )
    return fake


async def connect(client, headers, key=KEY, token=TOKEN):
    return await client.put(
        f"{API}/integrations/trello",
        json={"api_key": key, "token": token},
        headers=headers,
    )


async def do_import(client, headers, ids=("board1",)):
    res = await client.post(
        f"{API}/integrations/trello/import",
        json={"board_ids": list(ids)},
        headers=headers,
    )
    assert res.status_code == 200, res.text
    return res.json()["data"]


@pytest.fixture
async def other_headers(client):
    creds = {"email": "other@example.com", "password": "otherpassword123"}
    await client.post(f"{API}/auth/register", json=creds)
    res = await client.post(f"{API}/auth/login", json=creds)
    return {"Authorization": f"Bearer {res.json()['data']['access_token']}"}


class TestConnect:
    async def test_connect_validates_and_masks(self, client, auth_headers, trello):
        res = await connect(client, auth_headers)
        assert res.status_code == 200, res.text
        data = res.json()["data"]
        assert data["provider"] == "trello"
        assert data["account_label"] == "Deniz Yılmaz"
        assert data["status"] == "active"
        # tam deger asla donmez, sadece son 4 karakter
        assert data["masked_credentials"] == {"api_key": "…5678", "token": "…7890"}
        assert TOKEN not in res.text and KEY not in res.text

        listed = await client.get(f"{API}/integrations", headers=auth_headers)
        assert [a["provider"] for a in listed.json()["data"]] == ["trello"]
        assert TOKEN not in listed.text

    async def test_invalid_credentials_rejected(self, client, auth_headers, trello):
        res = await connect(client, auth_headers, token="wrong-token-123456")
        assert res.status_code == 422
        assert res.json()["error"]["code"] == "TRELLO_AUTH_FAILED"
        listed = await client.get(f"{API}/integrations", headers=auth_headers)
        assert listed.json()["data"] == []

    async def test_tokens_encrypted_at_rest(
        self, client, auth_headers, trello, test_session
    ):
        await connect(client, auth_headers)
        account = (
            await test_session.execute(select(IntegrationAccountEntity))
        ).scalar_one()
        assert KEY not in account.tokens_encrypted
        assert TOKEN not in account.tokens_encrypted
        assert crypto.decrypt_json(account.tokens_encrypted) == {
            "api_key": KEY,
            "token": TOKEN,
        }

    async def test_reconnect_replaces_not_duplicates(
        self, client, auth_headers, trello, test_session
    ):
        await connect(client, auth_headers)
        await connect(client, auth_headers)
        n = (
            await test_session.execute(
                select(func.count()).select_from(IntegrationAccountEntity)
            )
        ).scalar()
        assert n == 1

    async def test_disconnect_keeps_imported_data(self, client, auth_headers, trello):
        await connect(client, auth_headers)
        await do_import(client, auth_headers)
        res = await client.delete(f"{API}/integrations/trello", headers=auth_headers)
        assert res.status_code == 204
        listed = await client.get(f"{API}/integrations", headers=auth_headers)
        assert listed.json()["data"] == []
        boards = (await client.get(f"{API}/boards", headers=auth_headers)).json()["data"]
        assert "Spor Programı" in [b["name"] for b in boards]
        # bagli degil -> 404
        res = await client.get(f"{API}/integrations/trello/boards", headers=auth_headers)
        assert res.status_code == 404

    async def test_no_secrets_in_httpx_logs(self, client, auth_headers, trello, caplog):
        import logging

        with caplog.at_level(logging.INFO):
            await connect(client, auth_headers)
        assert TOKEN not in caplog.text


class TestImport:
    async def test_import_counts_and_content(self, client, auth_headers, trello):
        await connect(client, auth_headers)
        boards = await client.get(
            f"{API}/integrations/trello/boards", headers=auth_headers
        )
        assert boards.json()["data"] == [
            {
                "id": "board1",
                "name": "Spor Programı",
                "url": FIXTURE["url"],
                "already_imported": False,
            }
        ]

        [result] = await do_import(client, auth_headers)
        assert result["created_board"] is True and result["error"] is None
        assert result["lists"] == 3
        assert result["cards"] == 5
        assert result["checklist_items"] == 2
        assert result["notes"] == 2
        assert result["skipped_cards"] == 0

        detail = (
            await client.get(f"{API}/boards/{result['board_id']}", headers=auth_headers)
        ).json()["data"]
        assert detail["board"]["name"] == "Spor Programı"
        assert detail["board"]["color"] == "#f97316"
        assert detail["board"]["scope_description"] == "Antrenman ve beslenme işleri"
        lists = {lst["name"]: lst for lst in detail["lists"]}
        assert [lst["name"] for lst in detail["lists"]] == [
            "Yapılacak",
            "Yapılıyor",
            "Bitti",
        ]
        assert lists["Bitti"]["is_done_list"] is True

        cards = {c["title"]: c for c in detail["cards"]}
        assert set(cards) == {
            "Program hazırla",
            "Koşu ayakkabısı al",
            "Haftalık ölçüm",
            "Üyelik yenile",
            "Vitamin al",
        }
        # sira Trello pos'una gore
        todo = [
            c["title"]
            for c in sorted(detail["cards"], key=lambda c: c["position"])
            if c["list_id"] == lists["Yapılacak"]["id"]
        ]
        assert todo == ["Program hazırla", "Koşu ayakkabısı al", "Vitamin al"]
        # bitti listesi ve dueComplete -> tamamlandi
        assert cards["Üyelik yenile"]["status"] == "completed"
        assert cards["Vitamin al"]["status"] == "completed"
        assert cards["Haftalık ölçüm"]["status"] == "pending"
        assert cards["Koşu ayakkabısı al"]["due_date"].startswith("2026-11-20")
        assert {lb["name"] for lb in detail["labels"]} == {"Acil", "blue"}

        full = (
            await client.get(
                f"{API}/cards/{cards['Koşu ayakkabısı al']['id']}", headers=auth_headers
            )
        ).json()["data"]
        assert full["created_by"] == "integration"
        assert "Boyut 43" in full["description"] and "Mağaza" in full["description"]
        assert [i["text"] for i in full["checklist"]] == [
            "Bütçe belirle",
            "Mağazaları karşılaştır",
        ]
        assert [i["is_done"] for i in full["checklist"]] == [True, False]
        assert len(full["label_ids"]) == 2
        notes = [n["content"] for n in full["notes"]]
        assert "Deniz Yılmaz, 2026-11-02: Fiyatlara bak" in notes

        # etkinlik gecmisi entegrasyon aktoruyle
        activity = (
            await client.get(
                f"{API}/cards/{full['id']}/activity", headers=auth_headers
            )
        ).json()["data"]
        assert activity[-1]["actor"] == "integration"

        # board listesinde "zaten aktarildi" isareti
        boards = await client.get(
            f"{API}/integrations/trello/boards", headers=auth_headers
        )
        assert boards.json()["data"][0]["already_imported"] is True

    async def test_second_import_is_idempotent(
        self, client, auth_headers, trello, test_session
    ):
        await connect(client, auth_headers)
        await do_import(client, auth_headers)
        [again] = await do_import(client, auth_headers)
        assert again["created_board"] is False
        assert (again["lists"], again["cards"], again["checklist_items"], again["notes"]) == (
            0,
            0,
            0,
            0,
        )
        assert again["skipped_cards"] == 5
        n_cards = (
            await test_session.execute(select(func.count()).select_from(TaskEntity))
        ).scalar()
        assert n_cards == 5
        boards = (await client.get(f"{API}/boards", headers=auth_headers)).json()["data"]
        assert [b["name"] for b in boards].count("Spor Programı") == 1

    async def test_reimport_adds_only_new_objects(self, client, auth_headers, trello):
        await connect(client, auth_headers)
        await do_import(client, auth_headers)
        data = trello.boards["board1"]
        data["cards"].append(
            {
                "id": "c9",
                "name": "Yeni kart",
                "desc": "",
                "idList": "l-doing",
                "pos": 9000,
                "closed": False,
                "idLabels": [],
                "attachments": [],
                "checklists": [],
            }
        )
        c1 = next(c for c in data["cards"] if c["id"] == "c1")
        c1["checklists"][0]["checkItems"].append(
            {"id": "ci9", "name": "Yeni madde", "state": "incomplete", "pos": 3}
        )
        data["lists"].append({"id": "l-new", "name": "Yeni liste", "pos": 5000, "closed": False})
        [result] = await do_import(client, auth_headers)
        assert result["cards"] == 1
        assert result["lists"] == 1
        assert result["checklist_items"] == 1
        assert result["skipped_cards"] == 5

    async def test_local_edits_not_overwritten(self, client, auth_headers, trello):
        await connect(client, auth_headers)
        [first] = await do_import(client, auth_headers)
        detail = (
            await client.get(f"{API}/boards/{first['board_id']}", headers=auth_headers)
        ).json()["data"]
        card = next(c for c in detail["cards"] if c["title"] == "Program hazırla")
        await client.patch(
            f"{API}/cards/{card['id']}", json={"title": "Benim başlığım"}, headers=auth_headers
        )
        trello.boards["board1"]["cards"][1]["name"] = "Trello'da değişti"
        await do_import(client, auth_headers)
        after = (
            await client.get(f"{API}/cards/{card['id']}", headers=auth_headers)
        ).json()["data"]
        assert after["title"] == "Benim başlığım"

    async def test_deleted_local_board_is_recreated(self, client, auth_headers, trello):
        await connect(client, auth_headers)
        [first] = await do_import(client, auth_headers)
        res = await client.delete(
            f"{API}/boards/{first['board_id']}", headers=auth_headers
        )
        assert res.status_code == 204
        boards = await client.get(
            f"{API}/integrations/trello/boards", headers=auth_headers
        )
        assert boards.json()["data"][0]["already_imported"] is False
        [again] = await do_import(client, auth_headers)
        assert again["created_board"] is True
        assert again["cards"] == 5 and again["lists"] == 3

    async def test_user_deleted_card_not_reimported(self, client, auth_headers, trello):
        await connect(client, auth_headers)
        [first] = await do_import(client, auth_headers)
        detail = (
            await client.get(f"{API}/boards/{first['board_id']}", headers=auth_headers)
        ).json()["data"]
        card = next(c for c in detail["cards"] if c["title"] == "Haftalık ölçüm")
        await client.delete(f"{API}/cards/{card['id']}", headers=auth_headers)
        [again] = await do_import(client, auth_headers)
        assert again["cards"] == 0
        detail = (
            await client.get(f"{API}/boards/{first['board_id']}", headers=auth_headers)
        ).json()["data"]
        assert "Haftalık ölçüm" not in [c["title"] for c in detail["cards"]]

    async def test_external_links_recorded(
        self, client, auth_headers, trello, test_session
    ):
        await connect(client, auth_headers)
        await do_import(client, auth_headers)
        rows = (
            await test_session.execute(
                select(ExternalLinkEntity.entity_type, func.count()).group_by(
                    ExternalLinkEntity.entity_type
                )
            )
        ).all()
        assert dict(rows) == {
            "board": 1,
            "list": 3,
            "card": 5,
            "checklist_item": 2,
            "note": 2,
        }

    async def test_unknown_board_rejected(self, client, auth_headers, trello):
        await connect(client, auth_headers)
        res = await client.post(
            f"{API}/integrations/trello/import",
            json={"board_ids": ["someone-elses-board"]},
            headers=auth_headers,
        )
        assert res.status_code == 404
        res = await client.post(
            f"{API}/integrations/trello/import",
            json={"board_ids": []},
            headers=auth_headers,
        )
        assert res.status_code == 422


class TestOwnership:
    async def test_other_user_cannot_use_my_account(
        self, client, auth_headers, other_headers, trello
    ):
        await connect(client, auth_headers)
        listed = await client.get(f"{API}/integrations", headers=other_headers)
        assert listed.json()["data"] == []
        res = await client.get(
            f"{API}/integrations/trello/boards", headers=other_headers
        )
        assert res.status_code == 404
        res = await client.post(
            f"{API}/integrations/trello/import",
            json={"board_ids": ["board1"]},
            headers=other_headers,
        )
        assert res.status_code == 404
        res = await client.delete(f"{API}/integrations/trello", headers=other_headers)
        assert res.status_code == 404
        # benim hesabim yerinde
        listed = await client.get(f"{API}/integrations", headers=auth_headers)
        assert len(listed.json()["data"]) == 1

    async def test_requires_auth(self, client):
        res = await client.get(f"{API}/integrations")
        assert res.status_code in (401, 403)


class TestInbox:
    async def test_connect_creates_inbox_once(self, client, auth_headers, trello):
        await connect(client, auth_headers)
        await connect(client, auth_headers)
        boards = (await client.get(f"{API}/boards", headers=auth_headers)).json()["data"]
        inboxes = [b for b in boards if b["system_kind"] == "inbox"]
        assert len(inboxes) == 1
        inbox = inboxes[0]
        assert inbox["name"] == "Gelen Kutusu"
        assert inbox["privacy"] == "local_only"
        detail = (
            await client.get(f"{API}/boards/{inbox['id']}", headers=auth_headers)
        ).json()["data"]
        assert [lst["name"] for lst in detail["lists"]] == ["Gelen"]

    async def test_inbox_cannot_be_deleted_but_can_be_renamed(
        self, client, auth_headers, trello
    ):
        await connect(client, auth_headers)
        boards = (await client.get(f"{API}/boards", headers=auth_headers)).json()["data"]
        inbox = next(b for b in boards if b["system_kind"] == "inbox")
        res = await client.delete(f"{API}/boards/{inbox['id']}", headers=auth_headers)
        assert res.status_code == 409
        assert res.json()["error"]["code"] == "INBOX_PROTECTED"
        res = await client.patch(
            f"{API}/boards/{inbox['id']}", json={"name": "Toplanan"}, headers=auth_headers
        )
        assert res.status_code == 200
        assert res.json()["data"]["system_kind"] == "inbox"
        # yeniden adlandirilsa da ikinci inbox acilmaz
        await connect(client, auth_headers)
        boards = (await client.get(f"{API}/boards", headers=auth_headers)).json()["data"]
        assert len([b for b in boards if b["system_kind"] == "inbox"]) == 1
