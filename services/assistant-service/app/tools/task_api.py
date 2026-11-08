"""
task-api istemcisi. AI veriye SADECE buradan, kullanicinin kendi JWT'siyle erisir:
dogrulama, sahiplik kontrolu, activity log ve event'ler AI icin de aynen calisir.
"""

from typing import Any

import httpx

from app.config import settings


class TaskApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


class TaskApiClient:
    def __init__(self, token: str, transport: httpx.AsyncBaseTransport | None = None):
        self.client = httpx.AsyncClient(
            base_url=settings.task_api_url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=20,
            transport=transport,
        )

    async def close(self) -> None:
        await self.client.aclose()

    async def get(self, path: str, **params: Any) -> Any:
        clean = {k: v for k, v in params.items() if v is not None}
        return await self._send("GET", path, params=clean)

    async def write(self, method: str, path: str, body: Any | None = None) -> Any:
        """Yazma istegi. `X-Actor: ai`: task-api kaydi 'AI yapti' diye isaretler."""
        return await self._send(method, path, json=body, headers={"X-Actor": "ai"})

    async def _send(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            res = await self.client.request(method, path, **kwargs)
        except httpx.HTTPError as e:
            raise TaskApiError(503, f"Görev servisine ulaşılamadı: {e}") from e
        if res.status_code == 204:
            return None
        body = res.json() if res.content else {}
        if res.status_code >= 400 or not body.get("success", False):
            err = (body.get("error") or {}).get("message") or str(
                body.get("detail", "")
            )
            raise TaskApiError(res.status_code, err or f"HTTP {res.status_code}")
        return body.get("data")
