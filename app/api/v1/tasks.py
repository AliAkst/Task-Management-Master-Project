from datetime import UTC, datetime

from fastapi import APIRouter, status

from app.models.common import ApiResponse
from app.models.task import TaskCreate, TaskResponse, TaskUpdate
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_db_session
from app.db.entities import TaskEntity
from app.db.repositories.task import TaskRepository
from app.core.exceptions import TaskNotFoundException
from app.core.logging import get_logger

# Tasklarin log'u
logger = get_logger(__name__)

tasks_router = APIRouter(prefix="/tasks", tags=["Tasks"])


@tasks_router.post(
    "/", response_model=ApiResponse[TaskResponse], status_code=status.HTTP_201_CREATED
)
async def create_task(
    task_in: TaskCreate, session: AsyncSession = Depends(get_db_session)
):
    logger.info(f"Creating new task: {task_in.title}")
    repo = TaskRepository(session)

    new_task = TaskEntity(**task_in.model_dump())

    created_task = await repo.create(new_task)

    return ApiResponse(success=True, data=TaskResponse.model_validate(created_task))


@tasks_router.get("/", response_model=ApiResponse[list[TaskResponse]])
async def get_all_tasks(session: AsyncSession = Depends(get_db_session)):
    logger.info("Fetching all tasks")

    repo = TaskRepository(session)

    tasks = await repo.get_all()
    return ApiResponse(
        success=True, data=[TaskResponse.model_validate(t) for t in tasks]
    )


@tasks_router.get("/{task_id}", response_model=ApiResponse[TaskResponse])
async def get_task(task_id: int, session: AsyncSession = Depends(get_db_session)):
    logger.info(f"Fetching task with id: {task_id}")

    repo = TaskRepository(session)

    task = await repo.get_by_id(task_id)
    if not task:
        logger.warning(f"Task not found: {task_id}")
        raise TaskNotFoundException(task_id=task_id)
    return ApiResponse(success=True, data=TaskResponse.model_validate(task))


@tasks_router.put("/{task_id}", response_model=ApiResponse[TaskResponse])
async def update_task(
    task_id: int, task_in: TaskUpdate, session: AsyncSession = Depends(get_db_session)
):
    logger.info(f"Updating task with id: {task_id}")
    repo = TaskRepository(session)
    db_task = await repo.get_by_id(task_id)
    if not db_task:
        logger.warning(f"Task not found {task_id}")
        raise TaskNotFoundException(task_id=task_id)

    update_data = task_in.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_task, key, value)

    updated_task = await repo.update(db_task)
    return ApiResponse(success=True, data=TaskResponse.model_validate(updated_task))


@tasks_router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(task_id: int, session: AsyncSession = Depends(get_db_session)):
    logger.info(f"Deleting Task with id: {task_id}")
    repo = TaskRepository(session)

    db_task = await repo.get_by_id(task_id)
    if not db_task:
        logger.warning(f"Task not Found: {task_id}")
        raise TaskNotFoundException(task_id=task_id)

    await repo.delete(db_task)
    return ApiResponse(success=True, data=True)
