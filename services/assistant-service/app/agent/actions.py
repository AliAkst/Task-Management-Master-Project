"""
Izin kapisi: AI'in her yazma islemi kullanicinin o islem turu icin sectigi moda
gore isler (kullanici karar verir, varsayilan "sor"):

- ask   -> islem YAPILMAZ; oneri olarak kaydedilir, sohbette onay karti cikar.
           Modele "onay bekleniyor, yapildigini varsayma" denir.
- auto  -> hemen yapilir, kaydedilir, sohbette bilgi karti cikar.
- never -> arac modele hic gosterilmez (bkz. ToolBox.specs).

Onay/ret sonrasi sohbet gecmisindeki arac sonucu guncellenir; boylece model bir
sonraki mesajda neyin yapildigini / neden reddedildigini bilir.
"""

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import AiActionEntity, AiPermissionEntity, MessageEntity
from app.llm.types import ToolCall
from app.tools.task_api import TaskApiError
from app.tools.write_tools import ACTION_TYPES, PreparedAction, WriteTools

DEFAULT_MODE = "ask"
MODES = ("ask", "auto", "never")

PENDING_NOTE = (
    "İşlem YAPILMADI; kullanıcının onayı bekleniyor. Kullanıcıya ne önerdiğini kısaca "
    "söyle, onaylayabileceğini belirt. Yapıldığını asla söyleme."
)


@dataclass
class ToolResult:
    text: str  # modele giden arac sonucu (JSON metni)
    ok: bool
    action: dict[str, Any] | None = None  # sohbet arayuzune giden islem karti


def action_payload(a: AiActionEntity) -> dict[str, Any]:
    return {
        "id": a.id,
        "action_type": a.action_type,
        "summary": a.summary,
        "status": a.status,
        "result": a.result,
        "user_feedback": a.user_feedback,
    }


async def load_modes(session: AsyncSession, user_id: int) -> dict[str, str]:
    rows = await session.scalars(
        select(AiPermissionEntity).where(AiPermissionEntity.user_id == user_id)
    )
    modes = {t: DEFAULT_MODE for t in ACTION_TYPES}
    modes.update({r.action_type: r.mode for r in rows if r.action_type in ACTION_TYPES})
    return modes


async def set_mode(
    session: AsyncSession, user_id: int, action_type: str, mode: str
) -> None:
    row = await session.scalar(
        select(AiPermissionEntity).where(
            AiPermissionEntity.user_id == user_id,
            AiPermissionEntity.action_type == action_type,
        )
    )
    if row is None:
        session.add(
            AiPermissionEntity(user_id=user_id, action_type=action_type, mode=mode)
        )
    else:
        row.mode = mode
        row.updated_at = datetime.now(UTC)


async def record_outcome_in_history(
    session: AsyncSession, action: AiActionEntity
) -> None:
    """Sohbet gecmisindeki arac sonucunu islemin son durumuyla degistir."""
    if action.conversation_id is None or action.tool_call_id is None:
        return
    msg = await session.scalar(
        select(MessageEntity).where(
            MessageEntity.conversation_id == action.conversation_id,
            MessageEntity.tool_call_id == action.tool_call_id,
        )
    )
    if msg is None:
        return
    outcome: dict[str, Any] = {"status": action.status, "summary": action.summary}
    if action.status == "executed":
        outcome["note"] = "Kullanıcı onayladı ve işlem yapıldı."
        outcome["result"] = action.result
    elif action.status == "rejected":
        outcome["note"] = "Kullanıcı reddetti; işlem yapılmadı."
        if action.user_feedback:
            outcome["reason"] = action.user_feedback
    elif action.status == "failed":
        outcome["note"] = "Onaylandı ama işlem başarısız oldu."
        outcome["error"] = (action.result or {}).get("error")
    msg.content = json.dumps(outcome, ensure_ascii=False, default=str)


class ActionGate:
    def __init__(
        self,
        session_maker: async_sessionmaker[AsyncSession],
        writer: WriteTools,
        *,
        user_id: int,
        conversation_id: int | None,
        model_id: str | None,
        modes: dict[str, str],
    ):
        self.session_maker = session_maker
        self.writer = writer
        self.user_id = user_id
        self.conversation_id = conversation_id
        self.model_id = model_id
        self.modes = modes

    def allowed(self, action_type: str) -> bool:
        return self.modes.get(action_type, DEFAULT_MODE) != "never"

    async def handle(self, call: ToolCall, prepared: PreparedAction) -> ToolResult:
        mode = self.modes.get(prepared.action_type, DEFAULT_MODE)
        if mode == "never":
            return ToolResult(
                json.dumps(
                    {"error": "Kullanıcı bu tür işlemleri kapattı."}, ensure_ascii=False
                ),
                False,
            )
        action = AiActionEntity(
            user_id=self.user_id,
            conversation_id=self.conversation_id,
            tool_call_id=call.id,
            action_type=prepared.action_type,
            args=prepared.args,
            summary=prepared.summary,
            status="proposed",
            model_id=self.model_id,
        )
        if mode == "auto":
            try:
                action.result = await self.writer.execute(
                    prepared.action_type, prepared.args
                )
                action.status = "executed"
            except TaskApiError as e:
                action.result = {"error": e.message}
                action.status = "failed"
            action.decided_at = datetime.now(UTC)

        async with self.session_maker() as session:
            session.add(action)
            await session.commit()

        if action.status == "proposed":
            text = {
                "status": "pending_approval",
                "action_id": action.id,
                "summary": action.summary,
                "note": PENDING_NOTE,
            }
            ok = True
        elif action.status == "executed":
            text = {
                "status": "done",
                "summary": action.summary,
                "result": action.result,
            }
            ok = True
        else:
            text = {"status": "failed", "error": (action.result or {}).get("error")}
            ok = False
        return ToolResult(
            json.dumps(text, ensure_ascii=False, default=str),
            ok,
            action_payload(action),
        )
