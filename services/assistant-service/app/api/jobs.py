"""
Arka plan isleri (Faz 6a): gun sonu ozeti + ertesi gun plan onerisi.

RabbitMQ olmadan calisir: degerlendirme kaydedilince arayuz POST atar, is bu
servisin icinde (asyncio) surer; sayfa kapansa da devam eder. Isler sirayla
calisir (buyuk local model ayni anda iki kez yuklenmesin). Servis yeniden
baslarsa yarim kalan isler "failed" olur; kullanici yeniden baslatabilir.
"""

import asyncio
import logging
from datetime import UTC, date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update

import app.api.chat as chat_module
from app.agent.actions import action_payload
from app.agent.day_review import run_day_review
from app.api.deps import current_user, ok
from app.api.providers import load_cloud_config, user_background_model
from app.config import settings
from app.db.models import AiActionEntity, AiJobEntity
from app.llm.registry import cloud_label, is_local_model, parse_model_id
from app.llm.types import LLMError
from app.tools.task_api import TaskApiError

log = logging.getLogger(__name__)
router = APIRouter()
KIND = "day_review"
ACTIVE = ("queued", "running")
RESTART_ERROR = "Servis yeniden başladı; iş yarım kaldı. Yeniden başlatabilirsin."

_LOCK = asyncio.Lock()  # isler sirayla: buyuk model bir kez yuklensin
_TASKS: set[asyncio.Task] = set()


def model_label(model_id: str) -> str:
    provider, name = parse_model_id(model_id)
    return name if is_local_model(model_id) else cloud_label(provider, name)


def job_payload(job: AiJobEntity, action: AiActionEntity | None) -> dict[str, Any]:
    return {
        "id": job.id,
        "date": job.target_date,
        "status": job.status,
        "model_id": job.model_id,
        "model_label": model_label(job.model_id),
        "is_local": is_local_model(job.model_id),
        "result": job.result,
        "error": job.error,
        "action": action_payload(action) if action else None,
        "created_at": job.created_at,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
    }


async def _latest(session, user_id: int, day: str) -> AiJobEntity | None:
    return await session.scalar(
        select(AiJobEntity)
        .where(
            AiJobEntity.user_id == user_id,
            AiJobEntity.kind == KIND,
            AiJobEntity.target_date == day,
        )
        .order_by(AiJobEntity.id.desc())
        .limit(1)
    )


async def _payload(session, job: AiJobEntity | None) -> dict[str, Any] | None:
    if job is None:
        return None
    action = await session.get(AiActionEntity, job.action_id) if job.action_id else None
    return job_payload(job, action)


async def recover_stale_jobs() -> None:
    """Servis acilisinda: onceki surecten kalan yarim isleri kapat."""
    async with chat_module.session_maker() as session:
        await session.execute(
            update(AiJobEntity)
            .where(AiJobEntity.status.in_(ACTIVE))
            .values(status="failed", error=RESTART_ERROR, finished_at=datetime.now(UTC))
        )
        await session.commit()


async def _set(job_id: int, **values: Any) -> None:
    async with chat_module.session_maker() as session:
        job = await session.get(AiJobEntity, job_id)
        if job is not None:
            for k, v in values.items():
                setattr(job, k, v)
            await session.commit()


async def run_job(job_id: int, user: dict[str, Any], model_id: str, day: date) -> None:
    async with _LOCK:
        await _set(job_id, status="running", started_at=datetime.now(UTC))
        api = chat_module.TaskApiClient(user["token"])
        try:
            settings_data = await api.get("/settings/")
            tz = ZoneInfo(settings_data.get("timezone") or chat_module.DEFAULT_TZ)
            async with chat_module.session_maker() as session:
                cloud = (
                    None
                    if is_local_model(model_id)
                    else await load_cloud_config(
                        session, user["id"], parse_model_id(model_id)[0]
                    )
                )
            provider = chat_module.build_provider(
                model_id, cloud, timeout=settings.background_timeout_seconds
            )
            result, action_id = await run_day_review(
                api,
                provider,
                chat_module.session_maker,
                user_id=user["id"],
                day=day,
                tz=tz,
            )
            await _set(
                job_id,
                status="done",
                result=result,
                action_id=action_id,
                finished_at=datetime.now(UTC),
            )
        except (TaskApiError, LLMError, ValueError) as e:
            await _set(
                job_id,
                status="failed",
                error=getattr(e, "message", None) or str(e),
                finished_at=datetime.now(UTC),
            )
        except Exception:  # pragma: no cover - beklenmeyen hata isi asili birakmasin
            log.exception("day_review job %s failed", job_id)
            await _set(
                job_id,
                status="failed",
                error="Beklenmeyen bir hata oldu",
                finished_at=datetime.now(UTC),
            )
        finally:
            await api.close()


def _spawn(job_id: int, user: dict[str, Any], model_id: str, day: date) -> None:
    task = asyncio.create_task(run_job(job_id, user, model_id, day))
    _TASKS.add(task)
    task.add_done_callback(_TASKS.discard)


@router.post("/day-review/{day}")
async def start_day_review(day: date, user: dict = Depends(current_user)):
    """Gun ozeti + yarin plan onerisi isini baslatir (suruyorsa onu doner)."""
    async with chat_module.session_maker() as session:
        job = await _latest(session, user["id"], day.isoformat())
        if job is not None and job.status in ACTIVE:
            return ok(await _payload(session, job))
        installed = {m.id for m in await chat_module.list_local_models()}
        model_id = await user_background_model(session, user["id"], installed)
        if is_local_model(model_id) and model_id not in installed:
            raise HTTPException(
                422, f"{model_label(model_id)} kurulu değil ya da Ollama kapalı"
            )
        if not is_local_model(model_id):
            try:
                cloud = await load_cloud_config(
                    session, user["id"], parse_model_id(model_id)[0]
                )
                chat_module.build_provider(model_id, cloud)  # bagli mi (istek atmaz)
            except LLMError as e:
                raise HTTPException(422, str(e)) from e
        job = AiJobEntity(
            user_id=user["id"],
            kind=KIND,
            target_date=day.isoformat(),
            status="queued",
            model_id=model_id,
        )
        session.add(job)
        await session.commit()
        payload = await _payload(session, job)
    _spawn(job.id, user, model_id, day)
    return ok(payload)


@router.get("/day-review/{day}")
async def get_day_review(day: date, user: dict = Depends(current_user)):
    """O gun icin son is (yoksa null)."""
    async with chat_module.session_maker() as session:
        return ok(
            await _payload(session, await _latest(session, user["id"], day.isoformat()))
        )
