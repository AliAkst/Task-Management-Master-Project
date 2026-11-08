"""
ModelRouter: bu mesaj hangi modelle yanitlanacak?

Sira: mesajda elle secilen > acik board'un varsayilani > kullanicinin (local)
varsayilani. "Sadece local" board'un bulut varsayilani yok sayilir (gizlilik).
"""

from dataclasses import dataclass
from typing import Literal

from app.llm.registry import is_local_model
from app.tools.task_api import TaskApiClient, TaskApiError

Source = Literal["message", "board", "user"]


@dataclass
class Route:
    model_id: str
    source: Source


async def board_default_model(api: TaskApiClient, board_id: int) -> str | None:
    try:
        data = await api.get(f"/boards/{board_id}")
    except TaskApiError:
        return None  # board silinmis/erisilemiyor: kullanici varsayilanina dus
    board = data.get("board") or {}
    model_id = board.get("default_model_id")
    if not model_id:
        return None
    if board.get("privacy") == "local_only" and not is_local_model(model_id):
        return None
    return model_id


async def resolve_model(
    api: TaskApiClient,
    *,
    requested: str | None,
    board_id: int | None,
    user_default: str,
) -> Route:
    if requested:
        return Route(requested, "message")
    if board_id is not None:
        model_id = await board_default_model(api, board_id)
        if model_id:
            return Route(model_id, "board")
    return Route(user_default, "user")
