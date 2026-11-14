"""
Claude baglantisi (MCP) arac koprusu (Faz 13i). MCP SDK'sindan bagimsiz: arac listesi,
izin/gizlilik kurallari ve sonuc esleme burada; protokol baglantisi `mcp_server.py`'de.

Kurallar (K8):
- Okuma + kart/takvim/plan yazma araclari. Silme ve hafiza araclari YOK.
- Cloud model gibi davranilir: `local_only` board verisi cikmaz (ToolBox.create cloud=True,
  her cagride taze).
- Yazmalar `ActionGate`ten gecer: `ask` -> "Bekleyen islemler"e oneri, `auto` -> yapilir.
- PAT hicbir mesaja/loga yazilmaz.
"""

import json
import logging
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agent.actions import ActionGate, ToolResult, load_modes
from app.db.models import AiActionEntity
from app.llm.types import ToolCall
from app.notify.base import Notification, Notifier
from app.tools.read_tools import ToolBox
from app.tools.task_api import TaskApiAuthError, TaskApiClient, TaskApiError
from app.tools.write_tools import WRITE_SPECS, action_type_of

log = logging.getLogger(__name__)

MCP_MODEL_ID = "mcp:claude"
DEFAULT_TZ = "Europe/Istanbul"
WHOAMI_TTL_SECONDS = 60

MCP_READ: tuple[str, ...] = (
    "list_boards",
    "get_board",
    "search_cards",
    "get_card",
    "get_calendar",
    "get_day_plan",
    "get_stats_summary",
    "list_goals",
    "get_courses",
    "get_work_summary",
    "get_action_status",
)
MCP_WRITE: tuple[str, ...] = (
    "create_card",
    "update_card",
    "move_card",
    "schedule_card",
    "reschedule_card",
    "plan_day",
    "schedule_day",
    "create_event",
)
STATUS_TOOL = "ajanda_status"

NOT_AVAILABLE = "Bu araç Claude bağlantısında yok."
CLOSED = "Kullanıcı bu tür işlemleri kapattı."
APPROVAL_NOTE = (
    "Bu işlem henüz YAPILMADI. Kullanıcı Ajanda'da Asistan → Bekleyen işlemler'den "
    "onaylayınca yapılır. Sonucu get_action_status ile sorabilirsin; onaylanmadan "
    "'yaptım' deme."
)

GET_ACTION_STATUS_SCHEMA = {
    "type": "object",
    "properties": {"action_id": {"type": "integer"}},
    "required": ["action_id"],
}
GET_ACTION_STATUS_DESC = (
    "Önerdiğin bir işlemin durumunu sorar (proposed = kullanıcı henüz onaylamadı, "
    "executed = yapıldı, rejected = reddedildi, failed = başarısız)."
)


@dataclass(frozen=True)
class McpToolDef:
    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass
class McpReply:
    text: str
    is_error: bool = False


class BridgeError(Exception):
    """Ajanda'ya baglanilamadi / anahtar gecersiz (mesaj kullaniciya gider)."""


def connect_error_text(reason: str) -> str:
    return (
        f"Ajanda'ya bağlanılamadı: {reason}. Ajanda açık mı? Anahtar geçersizse "
        "Ajanda → Ayarlar → Claude bağlantısı'ndan yeni anahtar üret."
    )


REASON_KEY = "anahtar geçersiz ya da iptal edilmiş"
REASON_DOWN = "Ajanda kapalı ya da ulaşılamıyor"


def _write_specs() -> dict[str, Any]:
    return {s.name: s for s in WRITE_SPECS if s.name in MCP_WRITE}


def _error_text(raw: str) -> str:
    try:
        data = json.loads(raw)
    except ValueError:
        return raw
    if isinstance(data, dict) and isinstance(data.get("error"), str):
        return data["error"]
    return raw


class McpBridge:
    def __init__(
        self,
        session_maker: async_sessionmaker[AsyncSession],
        token: str,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        notifier: Notifier | None = None,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.session_maker = session_maker
        self._token = token
        self.transport = transport
        self.notifier = notifier or Notifier(session_maker)
        self._clock = clock
        self._user: dict[str, Any] | None = None
        self._user_until = 0.0

    # ---------------- kimlik ----------------
    def _client(self) -> TaskApiClient:
        return TaskApiClient(self._token, transport=self.transport, actor="mcp")

    async def whoami(self) -> dict[str, Any]:
        """PAT'in sahibi; 60 sn bellekte. Basarisizlikta BridgeError (belleklenmez)."""
        if self._user is not None and self._clock() < self._user_until:
            return self._user
        api = self._client()
        try:
            self._user = None
            user = await api.get("/auth/me")
        except TaskApiAuthError as e:
            raise BridgeError(REASON_KEY) from e
        except TaskApiError as e:
            raise BridgeError(REASON_DOWN if e.status >= 500 else REASON_KEY) from e
        finally:
            await api.close()
        if not isinstance(user, dict) or "id" not in user:
            raise BridgeError(REASON_KEY)
        self._user = user
        self._user_until = self._clock() + WHOAMI_TTL_SECONDS
        return user

    # ---------------- arac listesi ----------------
    async def list_tools(self) -> list[McpToolDef]:
        try:
            user = await self.whoami()
        except BridgeError:
            return [
                McpToolDef(
                    STATUS_TOOL,
                    "Ajanda bağlantı durumu",
                    {"type": "object", "properties": {}},
                )
            ]
        async with self.session_maker() as session:
            modes = await load_modes(session, user["id"])
        read = {s.name: s for s in ToolBox.read_specs()}
        writes = _write_specs()
        tools: list[McpToolDef] = []
        for name in MCP_READ:
            if name == "get_action_status":
                tools.append(
                    McpToolDef(name, GET_ACTION_STATUS_DESC, GET_ACTION_STATUS_SCHEMA)
                )
            else:
                s = read[name]
                tools.append(McpToolDef(name, s.description, s.parameters))
        for name in MCP_WRITE:
            if modes.get(action_type_of(name), "ask") == "never":
                continue
            s = writes[name]
            tools.append(
                McpToolDef(name, "[Onay gerekebilir] " + s.description, s.parameters)
            )
        return tools

    # ---------------- arac cagrisi ----------------
    async def call(self, name: str, arguments: dict[str, Any] | None) -> McpReply:
        args = arguments or {}
        try:
            user = await self.whoami()
        except BridgeError as e:
            return McpReply(connect_error_text(str(e)), True)
        if name == STATUS_TOOL:
            return McpReply(f"Ajanda bağlantısı çalışıyor (kullanıcı #{user['id']}).")
        if name not in MCP_READ and name not in MCP_WRITE:
            return McpReply(NOT_AVAILABLE, True)
        try:
            return await self._dispatch(user, name, args)
        except TaskApiAuthError:
            self._user = None
            return McpReply(connect_error_text(REASON_KEY), True)
        except TaskApiError as e:
            if e.status >= 500:
                return McpReply(connect_error_text(REASON_DOWN), True)
            return McpReply(e.message, True)
        except Exception:  # beklenmeyen hata protokolu dusurmesin; ayrinti stderr'e
            log.exception("mcp arac hatasi: %s", name)
            return McpReply("Beklenmeyen bir hata oluştu; ayrıntı Ajanda günlüğünde.", True)

    async def _dispatch(
        self, user: dict[str, Any], name: str, args: dict[str, Any]
    ) -> McpReply:
        if name == "get_action_status":
            return await self._action_status(user["id"], args)
        api = self._client()
        try:
            settings_data = await api.get("/settings/")
            try:
                tz = ZoneInfo(settings_data.get("timezone") or DEFAULT_TZ)
            except Exception:
                tz = ZoneInfo(DEFAULT_TZ)
            # Her cagrida yeniden: gizli board/kart kumesi taze (cloud = filtre acik)
            box = await ToolBox.create(api, cloud=True, tz=tz)
            async with self.session_maker() as session:
                modes = await load_modes(session, user["id"])
            box.gate = ActionGate(
                self.session_maker,
                box.writer,
                user_id=user["id"],
                conversation_id=None,
                model_id=MCP_MODEL_ID,
                modes=modes,
            )
            if name in MCP_WRITE and not box.gate.allowed(action_type_of(name)):
                return McpReply(CLOSED, True)
            call = ToolCall(id="mcp-" + uuid.uuid4().hex[:12], name=name, arguments=args)
            result = await box.execute(call)
        finally:
            await api.close()
        if name in MCP_WRITE:
            return await self._write_reply(user["id"], result)
        return McpReply(
            result.text if result.ok else _error_text(result.text), not result.ok
        )

    async def _write_reply(self, user_id: int, result: ToolResult) -> McpReply:
        if result.question is not None:
            return McpReply(
                f"SORU: {result.question.text}\nKullanıcıya sor ve cevabına göre "
                "schedule_day'i saatleri/öğeleri düzelterek yeniden çağır."
            )
        action = result.action
        if action is None:  # dogrulama / gizlilik / task-api hatasi
            return McpReply(_error_text(result.text), True)
        status = action["status"]
        if status == "proposed":
            await self._notify(user_id, action["summary"])
            return McpReply(
                f"ONAY BEKLİYOR (#{action['id']}): {action['summary']}\n{APPROVAL_NOTE}"
            )
        if status == "executed":
            return McpReply(f"YAPILDI: {action['summary']}")
        error = (action.get("result") or {}).get("error") or "bilinmeyen hata"
        return McpReply(f"BAŞARISIZ: {error}", True)

    async def _notify(self, user_id: int, summary: str) -> None:
        first = (summary or "").splitlines()[0][:120] if summary else ""
        try:
            await self.notifier.send(
                user_id, Notification("mcp", "Claude bir işlem önerdi", first)
            )
        except Exception:  # bildirim hatasi yazma sonucunu bozmasin
            log.exception("mcp bildirimi gonderilemedi")

    async def _action_status(self, user_id: int, args: dict[str, Any]) -> McpReply:
        raw = args.get("action_id")
        if not isinstance(raw, int) or isinstance(raw, bool):
            return McpReply("action_id tam sayı olmalı", True)
        async with self.session_maker() as session:
            row = await session.scalar(
                select(AiActionEntity).where(
                    AiActionEntity.id == raw, AiActionEntity.user_id == user_id
                )
            )
        if row is None:
            return McpReply("İşlem bulunamadı", True)
        out: dict[str, Any] = {
            "id": row.id,
            "status": row.status,
            "summary": row.summary,
        }
        if row.status == "failed":
            out["error"] = (row.result or {}).get("error")
        if row.user_feedback:
            out["user_feedback"] = row.user_feedback
        return McpReply(json.dumps(out, ensure_ascii=False))
