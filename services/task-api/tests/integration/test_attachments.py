"""Faz 8c: kart ekleri (yukleme, indirme guvenligi, silme yollari, yetim temizligi)."""

import hashlib
import os
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from httpx import AsyncClient

from app.config import settings
from app.services.attachment import sanitize_filename
from app.services.attachment_storage import (
    LocalAttachmentStorage,
    get_storage,
    make_attachment_token,
)
from tests.integration.test_boards_cards import API, create_board, create_card

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64


@pytest.fixture(autouse=True)
def storage_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "attachments_dir", str(tmp_path / "att"))
    return tmp_path / "att"


@pytest.fixture
async def other_headers(client: AsyncClient) -> dict[str, str]:
    creds = {"email": "other@example.com", "password": "otherpassword123"}
    await client.post(f"{API}/auth/register", json=creds)
    res = await client.post(f"{API}/auth/login", json=creds)
    return {"Authorization": f"Bearer {res.json()['data']['access_token']}"}


@pytest.fixture
async def board(client: AsyncClient, auth_headers):
    return await create_board(client, auth_headers, name="Ekler")


@pytest.fixture
async def card(client: AsyncClient, auth_headers, board):
    return await create_card(client, auth_headers, board["lists"][0]["id"], "Kart")


async def upload(
    client, headers, card_id, name="a.txt", data=b"merhaba", ctype=None, **form
):
    return await client.post(
        f"{API}/cards/{card_id}/attachments",
        files={"file": (name, data, ctype or "application/octet-stream")},
        data={k: str(v) for k, v in form.items()},
        headers=headers,
    )


async def make(client, headers, card_id, **kw):
    res = await upload(client, headers, card_id, **kw)
    assert res.status_code == 201, res.text
    return res.json()["data"]


def files_on_disk(root) -> list:
    return [p for p in root.rglob("*") if p.is_file()] if root.exists() else []


class TestUploadAndDownload:
    async def test_upload_list_download(
        self, client, auth_headers, card, storage_dir
    ):
        att = await make(client, auth_headers, card["id"], name="rapor.txt")
        assert att["filename"] == "rapor.txt" and att["size_bytes"] == 7
        assert att["mime_type"] == "text/plain" and att["is_image"] is False
        listed = await client.get(
            f"{API}/cards/{card['id']}/attachments", headers=auth_headers
        )
        assert [a["id"] for a in listed.json()["data"]] == [att["id"]]

        # imzali URL: Authorization olmadan da iner; icerik birebir
        res = await client.get(att["url"])
        assert res.status_code == 200 and res.content == b"merhaba"
        assert hashlib.sha256(res.content).hexdigest() == hashlib.sha256(
            b"merhaba"
        ).hexdigest()
        # diskte tek dosya, kullanici id'li klasorde, uzantisiz
        (f,) = files_on_disk(storage_dir)
        assert f.suffix == "" and f.parent.name == str(card["user_id"])

    async def test_detail_and_summary_include_attachments(
        self, client, auth_headers, card, board
    ):
        att = await make(client, auth_headers, card["id"])
        detail = (
            await client.get(f"{API}/cards/{card['id']}", headers=auth_headers)
        ).json()["data"]
        assert detail["attachment_count"] == 1
        assert detail["attachments"][0]["id"] == att["id"]
        assert "token=" in detail["attachments"][0]["url"]
        board_data = (
            await client.get(f"{API}/boards/{board['board']['id']}", headers=auth_headers)
        ).json()["data"]
        (summary,) = [c for c in board_data["cards"] if c["id"] == card["id"]]
        assert summary["attachment_count"] == 1

    async def test_sha256_stored(self, client, auth_headers, card, test_session):
        from sqlalchemy import select

        from app.db.entities import CardAttachmentEntity

        await make(client, auth_headers, card["id"], data=PNG, name="x.png")
        row = (await test_session.execute(select(CardAttachmentEntity))).scalar_one()
        assert row.sha256 == hashlib.sha256(PNG).hexdigest()

    async def test_too_large_413_and_no_leftover(
        self, client, auth_headers, card, storage_dir, monkeypatch
    ):
        monkeypatch.setattr(settings, "attachments_max_mb", 1)
        res = await upload(
            client, auth_headers, card["id"], data=b"x" * (1024 * 1024 + 1)
        )
        assert res.status_code == 413
        assert res.json()["error"]["code"] == "ATTACHMENT_TOO_LARGE"
        assert files_on_disk(storage_dir) == []
        ok = await upload(client, auth_headers, card["id"], data=b"x" * 1024 * 1024)
        assert ok.status_code == 201

    @pytest.mark.parametrize("name", ["virus.exe", "a.PS1", "setup.msi", "x.lnk"])
    async def test_blocked_extension_422(
        self, client, auth_headers, card, storage_dir, name
    ):
        res = await upload(client, auth_headers, card["id"], name=name)
        assert res.status_code == 422
        assert res.json()["error"]["code"] == "ATTACHMENT_TYPE_BLOCKED"
        assert files_on_disk(storage_dir) == []

    async def test_code_files_allowed(self, client, auth_headers, card):
        for name in ("a.py", "b.js", "c.ts"):
            await make(client, auth_headers, card["id"], name=name)

    async def test_mime_from_extension_not_client(self, client, auth_headers, card):
        att = await make(
            client, auth_headers, card["id"], name="foto.png", data=PNG, ctype="text/html"
        )
        assert att["mime_type"] == "image/png" and att["is_image"] is True
        unknown = await make(client, auth_headers, card["id"], name="dosya.zzzunk")
        assert unknown["mime_type"] == "application/octet-stream"

    async def test_filename_sanitized(self, client, auth_headers, card):
        att = await make(client, auth_headers, card["id"], name="../../x.txt")
        assert att["filename"] == "x.txt"
        att2 = await make(client, auth_headers, card["id"], name="..\\..\\y.txt")
        assert att2["filename"] == "y.txt"

    def test_sanitize_filename_unit(self):
        assert sanitize_filename("../../x.txt") == "x.txt"
        assert sanitize_filename("a\x00b\x1f.txt") == "ab.txt"
        assert sanitize_filename("") == "dosya" and sanitize_filename("..") == "dosya"
        long = sanitize_filename("a" * 400 + ".pdf")
        assert len(long) == 200 and long.endswith(".pdf")


class TestDownloadSecurity:
    async def test_inline_types_and_headers(self, client, auth_headers, card):
        png = await make(client, auth_headers, card["id"], name="a.png", data=PNG)
        res = await client.get(png["url"])
        assert res.headers["content-type"] == "image/png"
        assert res.headers["content-disposition"].startswith("inline")
        assert res.headers["x-content-type-options"] == "nosniff"
        csp = res.headers["content-security-policy"]
        assert "default-src 'none'" in csp and "sandbox" in csp
        assert res.headers["cache-control"] == "private, max-age=3600"
        forced = await client.get(png["url"] + "&download=1")
        assert forced.headers["content-disposition"].startswith("attachment")

        pdf = await make(client, auth_headers, card["id"], name="a.pdf", data=b"%PDF-")
        res = await client.get(pdf["url"])
        assert res.headers["content-disposition"].startswith("inline")

    async def test_svg_and_html_always_attachment(self, client, auth_headers, card):
        for name in ("a.svg", "a.html", "a.txt"):
            att = await make(
                client, auth_headers, card["id"], name=name, data=b"<svg onload=1>"
            )
            res = await client.get(att["url"])
            assert res.headers["content-disposition"].startswith("attachment"), name
            assert res.headers["x-content-type-options"] == "nosniff"

    async def test_unicode_filename_rfc5987(self, client, auth_headers, card):
        att = await make(client, auth_headers, card["id"], name="rapor şğ.txt")
        cd = (await client.get(att["url"])).headers["content-disposition"]
        assert "filename*=UTF-8''rapor%20%C5%9F%C4%9F.txt" in cd

    async def test_token_expired_wrong_purpose_and_garbage(
        self, client, auth_headers, card, test_user
    ):
        att = await make(client, auth_headers, card["id"])
        uid = test_user["user"]["id"]

        def forge(**over):
            payload = {
                "sub": str(uid),
                "aid": att["id"],
                "purpose": "attachment",
                "exp": datetime.now(UTC) + timedelta(minutes=5),
                **over,
            }
            return jwt.encode(
                payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm
            )

        base = f"{API}/attachments/{att['id']}/download"
        assert (await client.get(base, params={"token": forge()})).status_code == 200
        expired = forge(exp=datetime.now(UTC) - timedelta(minutes=1))
        assert (await client.get(base, params={"token": expired})).status_code == 401
        wrong = forge(purpose="oauth_state")
        assert (await client.get(base, params={"token": wrong})).status_code == 401
        assert (await client.get(base, params={"token": "xyz"})).status_code == 401
        assert (await client.get(base)).status_code == 401
        # baska bir eke ait token
        assert (
            await client.get(base, params={"token": forge(aid=att["id"] + 99)})
        ).status_code == 404

    async def test_other_users_token_404(
        self, client, auth_headers, other_headers, card
    ):
        att = await make(client, auth_headers, card["id"])
        me = await client.get(f"{API}/auth/me", headers=other_headers)
        other_id = me.json()["data"]["id"]
        token = make_attachment_token(other_id, att["id"])
        res = await client.get(
            f"{API}/attachments/{att['id']}/download", params={"token": token}
        )
        assert res.status_code == 404

    async def test_authorization_header_download(
        self, client, auth_headers, other_headers, card
    ):
        att = await make(client, auth_headers, card["id"])
        path = f"{API}/attachments/{att['id']}/download"
        ok = await client.get(path, headers=auth_headers)
        assert ok.status_code == 200 and ok.content == b"merhaba"
        assert (await client.get(path, headers=other_headers)).status_code == 404

    async def test_other_users_card_upload_and_list_404(
        self, client, auth_headers, other_headers, card, storage_dir
    ):
        res = await upload(client, other_headers, card["id"])
        assert res.status_code == 404 and files_on_disk(storage_dir) == []
        res = await client.get(
            f"{API}/cards/{card['id']}/attachments", headers=other_headers
        )
        assert res.status_code == 404
        att = await make(client, auth_headers, card["id"])
        res = await client.delete(
            f"{API}/attachments/{att['id']}", headers=other_headers
        )
        assert res.status_code == 404

    async def test_storage_path_rejects_traversal(self, storage_dir):
        st = LocalAttachmentStorage(storage_dir)
        for bad in ("../../etc/passwd", "1/../../x", "1/abc", "/abs/path"):
            with pytest.raises(ValueError):
                st.path(bad)


class TestDeletion:
    async def test_delete_attachment_removes_file(
        self, client, auth_headers, card, storage_dir
    ):
        att = await make(client, auth_headers, card["id"])
        assert len(files_on_disk(storage_dir)) == 1
        res = await client.delete(f"{API}/attachments/{att['id']}", headers=auth_headers)
        assert res.status_code == 204 and files_on_disk(storage_dir) == []
        assert (await client.get(att["url"])).status_code == 404

    async def test_note_attachment_and_note_delete_keeps_file(
        self, client, auth_headers, card, storage_dir
    ):
        note = (
            await client.post(
                f"{API}/cards/{card['id']}/notes",
                json={"content": "not"},
                headers=auth_headers,
            )
        ).json()["data"]
        att = await make(client, auth_headers, card["id"], note_id=note["id"])
        assert att["note_id"] == note["id"]
        res = await client.delete(f"{API}/notes/{note['id']}", headers=auth_headers)
        assert res.status_code == 204
        detail = (
            await client.get(f"{API}/cards/{card['id']}", headers=auth_headers)
        ).json()["data"]
        assert [a["note_id"] for a in detail["attachments"]] == [None]
        assert len(files_on_disk(storage_dir)) == 1

    async def test_note_must_belong_to_card(self, client, auth_headers, board, card):
        other_card = await create_card(
            client, auth_headers, board["lists"][0]["id"], "Baska"
        )
        note = (
            await client.post(
                f"{API}/cards/{other_card['id']}/notes",
                json={"content": "n"},
                headers=auth_headers,
            )
        ).json()["data"]
        res = await upload(client, auth_headers, card["id"], note_id=note["id"])
        assert res.status_code == 422

    async def test_card_delete_removes_rows_and_files(
        self, client, auth_headers, card, storage_dir, test_session
    ):
        from sqlalchemy import func, select

        from app.db.entities import CardAttachmentEntity

        await make(client, auth_headers, card["id"], name="1.txt")
        await make(client, auth_headers, card["id"], name="2.txt")
        assert len(files_on_disk(storage_dir)) == 2
        res = await client.delete(f"{API}/cards/{card['id']}", headers=auth_headers)
        assert res.status_code == 204
        assert files_on_disk(storage_dir) == []
        count = await test_session.scalar(
            select(func.count()).select_from(CardAttachmentEntity)
        )
        assert count == 0

    async def test_board_delete_removes_rows_and_files(
        self, client, auth_headers, board, card, storage_dir, test_session
    ):
        from sqlalchemy import func, select

        from app.db.entities import CardAttachmentEntity

        await make(client, auth_headers, card["id"])
        res = await client.delete(
            f"{API}/boards/{board['board']['id']}", headers=auth_headers
        )
        assert res.status_code == 204
        assert files_on_disk(storage_dir) == []
        count = await test_session.scalar(
            select(func.count()).select_from(CardAttachmentEntity)
        )
        assert count == 0

    async def test_archive_keeps_attachments(
        self, client, auth_headers, card, storage_dir
    ):
        await make(client, auth_headers, card["id"])
        res = await client.patch(
            f"{API}/cards/{card['id']}", json={"is_archived": True}, headers=auth_headers
        )
        assert res.status_code == 200 and res.json()["data"]["attachment_count"] == 1
        assert len(files_on_disk(storage_dir)) == 1

    async def test_series_copy_has_no_attachments(
        self, client, auth_headers, board, storage_dir
    ):
        card = await create_card(
            client, auth_headers, board["lists"][0]["id"], "Tekrar"
        )
        await make(client, auth_headers, card["id"])
        res = await client.put(
            f"{API}/cards/{card['id']}/recurrence",
            json={"rule": "FREQ=DAILY"},
            headers=auth_headers,
        )
        series_id = res.json()["data"]["series_id"]
        await client.patch(
            f"{API}/cards/{card['id']}",
            json={"status": "completed"},
            headers=auth_headers,
        )
        data = (
            await client.get(f"{API}/boards/{board['board']['id']}", headers=auth_headers)
        ).json()["data"]
        (nxt,) = [
            c for c in data["cards"] if c["series_id"] == series_id and c["id"] != card["id"]
        ]
        assert nxt["attachment_count"] == 0
        assert len(files_on_disk(storage_dir)) == 1


class TestOrphanSweep:
    async def test_sweep_removes_only_old_unknown_files(self, storage_dir):
        st = get_storage()
        user_dir = storage_dir / "7"
        user_dir.mkdir(parents=True)
        old_orphan = user_dir / ("a" * 32)
        new_orphan = user_dir / ("b" * 32)
        known = user_dir / ("c" * 32)
        old_tmp = user_dir / ".tmp-xyz"
        for f in (old_orphan, new_orphan, known, old_tmp):
            f.write_bytes(b"x")
        old = (datetime.now(UTC) - timedelta(hours=30)).timestamp()
        for f in (old_orphan, known, old_tmp):
            os.utime(f, (old, old))
        removed = st.sweep_orphans({f"7/{'c' * 32}"}, timedelta(hours=24))
        assert removed == 2
        assert not old_orphan.exists() and not old_tmp.exists()
        assert new_orphan.exists() and known.exists()

    async def test_sweep_missing_root_is_noop(self):
        assert get_storage().sweep_orphans(set(), timedelta(hours=24)) == 0
