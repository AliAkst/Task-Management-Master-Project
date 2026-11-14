"""Denetim D2: asistan servisi PAT'i kabul etmez (403); JWT akışı değişmez."""

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

import app.api.deps as deps_module
from app.main import app

API = "/api/v1/assistant"
PAT = {"Authorization": "Bearer pat_abcdefghijklmnop"}


@pytest.fixture
async def raw_client(monkeypatch):
    calls: list[str] = []

    class FakeClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, headers=None):
            calls.append(url)
            return httpx.Response(
                200,
                json={"data": {"id": 1, "email": "u@x.com"}},
                request=httpx.Request("GET", url),
            )

    monkeypatch.setattr(deps_module.httpx, "AsyncClient", FakeClient)
    deps_module._CACHE.clear()
    app.dependency_overrides.clear()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        c.calls = calls  # type: ignore[attr-defined]
        yield c
    deps_module._CACHE.clear()


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("GET", "/permissions", None),
        ("PUT", "/permissions/delete_card", {"mode": "auto"}),
        ("POST", "/actions/1/approve", None),
        ("POST", "/actions/1/reject", None),
        ("POST", "/chat", {"message": "merhaba"}),
    ],
)
async def test_pat_is_forbidden_without_asking_task_api(raw_client, method, path, body):
    res = await raw_client.request(method, f"{API}{path}", json=body, headers=PAT)
    assert res.status_code == 403, res.text
    assert raw_client.calls == []


async def test_jwt_still_goes_through_task_api(raw_client):
    res = await raw_client.get(
        f"{API}/permissions", headers={"Authorization": "Bearer a.b.c"}
    )
    assert res.status_code != 403
    assert len(raw_client.calls) == 1
