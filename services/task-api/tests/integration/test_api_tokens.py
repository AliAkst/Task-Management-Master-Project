"""Kisisel erisim jetonu (PAT) testleri (Faz 13b)."""

import hashlib
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, text

from app.db.entities.api_token import ApiTokenEntity
from tests.integration.test_boards_cards import (
    API,
    create_board,
    create_card,
    other_headers,  # noqa: F401  (fixture)
)


async def make_token(client, headers, *, scopes=None, name="Test", **extra):
    res = await client.post(
        f"{API}/auth/tokens",
        json={"name": name, "scopes": ["read"] if scopes is None else scopes, **extra},
        headers=headers,
    )
    return res


def bearer(token: str, **extra) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", **extra}


@pytest.fixture
async def read_pat(client, auth_headers) -> str:
    res = await make_token(client, auth_headers, scopes=["read"])
    assert res.status_code == 201, res.text
    return res.json()["data"]["token"]


@pytest.fixture
async def write_pat(client, auth_headers) -> str:
    res = await make_token(client, auth_headers, scopes=["read", "write"])
    assert res.status_code == 201, res.text
    return res.json()["data"]["token"]


class TestCreateAndList:
    async def test_create_returns_token_once(self, client, auth_headers):
        res = await make_token(client, auth_headers, name="MCP", expires_in_days=30)
        assert res.status_code == 201
        data = res.json()["data"]
        assert data["token"].startswith("pat_")
        assert data["token_hint"] == data["token"][:10] + "…"
        assert data["scopes"] == ["read"]
        assert data["expires_at"] is not None

        listing = (await client.get(f"{API}/auth/tokens", headers=auth_headers)).json()[
            "data"
        ]
        assert [t["id"] for t in listing] == [data["id"]]
        dumped = str(listing)
        assert data["token"] not in dumped
        assert "token_hash" not in dumped
        assert "token'" not in dumped  # 'token' anahtari liste yanitinda yok

    async def test_write_scope_implies_read_and_validation(
        self, client, auth_headers
    ):
        res = await make_token(client, auth_headers, scopes=["write"])
        assert res.json()["data"]["scopes"] == ["read", "write"]
        assert (await make_token(client, auth_headers, scopes=[])).status_code == 422
        assert (
            await make_token(client, auth_headers, scopes=["admin"])
        ).status_code == 422
        assert (await make_token(client, auth_headers, name="")).status_code == 422
        assert (
            await make_token(client, auth_headers, expires_in_days=0)
        ).status_code == 422

    async def test_plaintext_not_stored(self, client, auth_headers, test_session):
        token = (await make_token(client, auth_headers)).json()["data"]["token"]
        row = (await test_session.execute(select(ApiTokenEntity))).scalars().one()
        assert row.token_hash == hashlib.sha256(token.encode()).hexdigest()
        assert len(row.token_hash) == 64
        rows = (await test_session.execute(text("SELECT * FROM api_tokens"))).all()
        assert all(token not in str(v) for r in rows for v in r)

    async def test_eleventh_token_conflict(self, client, auth_headers):
        for i in range(10):
            res = await make_token(client, auth_headers, name=f"t{i}")
            assert res.status_code == 201
        res = await make_token(client, auth_headers, name="fazla")
        assert res.status_code == 409
        assert res.json()["error"]["code"] == "TOO_MANY_TOKENS"


class TestPatAccess:
    async def test_read_pat_can_get_but_not_write(self, client, auth_headers, read_pat):
        res = await client.get(f"{API}/boards", headers=bearer(read_pat))
        assert res.status_code == 200
        board = await create_board(client, auth_headers)
        res = await client.post(
            f"{API}/cards",
            json={"list_id": board["lists"][0]["id"], "title": "x"},
            headers=bearer(read_pat),
        )
        assert res.status_code == 403
        assert res.json()["error"]["code"] == "PAT_SCOPE"

    async def test_write_pat_creates_card_with_mcp_actor(
        self, client, auth_headers, write_pat
    ):
        board = await create_board(client, auth_headers)
        res = await client.post(
            f"{API}/cards",
            json={"list_id": board["lists"][0]["id"], "title": "MCP kartı"},
            headers=bearer(write_pat, **{"X-Actor": "mcp"}),
        )
        assert res.status_code == 201, res.text
        card_id = res.json()["data"]["id"]
        history = (
            await client.get(f"{API}/cards/{card_id}/activity", headers=auth_headers)
        ).json()["data"]
        assert {a["actor"] for a in history} == {"mcp"}

    async def test_forbidden_paths_with_pat(self, client, write_pat):
        h = bearer(write_pat)
        for method, path in [
            ("POST", "/auth/tokens"),
            ("GET", "/auth/tokens"),
            ("GET", "/integrations"),
            ("PUT", "/settings/"),
            ("POST", "/cards/1/attachments"),
            ("GET", "/cards/1/attachments"),
            ("GET", "/attachments/1/download"),
        ]:
            res = await client.request(
                method, f"{API}{path}", headers=h, json={"x": 1} if method != "GET" else None
            )
            assert res.status_code == 403, (method, path, res.text)
            assert res.json()["error"]["code"] == "PAT_FORBIDDEN", (method, path)

    async def test_allowed_exceptions(self, client, auth_headers, read_pat):
        h = bearer(read_pat)
        assert (await client.get(f"{API}/auth/me", headers=h)).status_code == 200
        assert (await client.get(f"{API}/settings/", headers=h)).status_code == 200
        res = await client.post(
            f"{API}/cards/parse-title",
            json={"text": "yarın spor"},
            headers=h,
        )
        assert res.status_code == 200, res.text

    async def test_revoke_then_401(self, client, auth_headers):
        data = (await make_token(client, auth_headers)).json()["data"]
        token = data["token"]
        assert (
            await client.get(f"{API}/boards", headers=bearer(token))
        ).status_code == 200
        res = await client.delete(f"{API}/auth/tokens/{data['id']}", headers=auth_headers)
        assert res.status_code == 204
        assert (
            await client.get(f"{API}/boards", headers=bearer(token))
        ).status_code == 401
        listing = (await client.get(f"{API}/auth/tokens", headers=auth_headers)).json()[
            "data"
        ]
        assert listing == []

    async def test_expired_token_401(self, client, auth_headers, test_session):
        data = (
            await make_token(client, auth_headers, expires_in_days=5)
        ).json()["data"]
        row = (await test_session.execute(select(ApiTokenEntity))).scalars().one()
        row.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        await test_session.commit()
        res = await client.get(f"{API}/boards", headers=bearer(data["token"]))
        assert res.status_code == 401

    async def test_unknown_pat_401(self, client):
        res = await client.get(f"{API}/boards", headers=bearer("pat_yok-boyle-bir-anahtar"))
        assert res.status_code == 401

    async def test_delete_other_users_token_404(
        self, client, auth_headers, other_headers  # noqa: F811
    ):
        data = (await make_token(client, auth_headers)).json()["data"]
        res = await client.delete(f"{API}/auth/tokens/{data['id']}", headers=other_headers)
        assert res.status_code == 404
        res = await client.delete(f"{API}/auth/tokens/99999", headers=auth_headers)
        assert res.status_code == 404
        assert (
            await client.get(f"{API}/auth/tokens", headers=other_headers)
        ).json()["data"] == []

    async def test_pat_cannot_reach_other_users_card(
        self, client, auth_headers, other_headers, read_pat  # noqa: F811
    ):
        board = await create_board(client, other_headers)
        card = await create_card(client, other_headers, board["lists"][0]["id"], "Gizli")
        res = await client.get(f"{API}/cards/{card['id']}", headers=bearer(read_pat))
        assert res.status_code == 404

    async def test_last_used_at_updates(self, client, auth_headers, read_pat):
        before = (await client.get(f"{API}/auth/tokens", headers=auth_headers)).json()[
            "data"
        ][0]
        assert before["last_used_at"] is None
        await client.get(f"{API}/boards", headers=bearer(read_pat))
        after = (await client.get(f"{API}/auth/tokens", headers=auth_headers)).json()[
            "data"
        ][0]
        assert after["last_used_at"] is not None

    async def test_jwt_still_works_for_token_endpoints(self, client, auth_headers):
        assert (await make_token(client, auth_headers)).status_code == 201


class TestAttachmentUrlSideDoor:
    """Denetim D1: PAT kart detayından imzalı ek URL'si alamaz."""

    async def test_pat_card_detail_has_no_attachment_url(
        self, client, auth_headers, read_pat, tmp_path, monkeypatch
    ):
        from app.config import settings

        monkeypatch.setattr(settings, "attachments_dir", str(tmp_path / "att"))
        board = await create_board(client, auth_headers)
        card = await create_card(client, auth_headers, board["lists"][0]["id"], "Ekli")
        up = await client.post(
            f"{API}/cards/{card['id']}/attachments",
            files={"file": ("a.txt", b"gizli", "text/plain")},
            headers=auth_headers,
        )
        assert up.status_code == 201, up.text

        jwt_detail = (
            await client.get(f"{API}/cards/{card['id']}", headers=auth_headers)
        ).json()["data"]
        assert "token=" in jwt_detail["attachments"][0]["url"]

        pat_res = await client.get(f"{API}/cards/{card['id']}", headers=bearer(read_pat))
        assert pat_res.status_code == 200
        att = pat_res.json()["data"]["attachments"][0]
        assert att["url"] is None
        assert att["filename"] == "a.txt"
        assert "token=" not in str(pat_res.json())
