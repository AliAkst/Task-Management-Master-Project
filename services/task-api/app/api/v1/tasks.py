from fastapi import APIRouter, Query, status

from app.api.dependencies import CurrentUserDep, TaskServiceDep
from app.models.common import ApiResponse, PaginatedResponse, PaginationParams
from app.models.task import (
    TaskCreate,
    TaskFilter,
    TaskPriority,
    TaskResponse,
    TaskStatus,
    TaskUpdate,
)

tasks_router = APIRouter(prefix="/tasks", tags=["Tasks"])


@tasks_router.post(
    "/", response_model=ApiResponse[TaskResponse], status_code=status.HTTP_201_CREATED
)
async def create_task(
    task_in: TaskCreate, service: TaskServiceDep, current_user: CurrentUserDep
):
    """Yeni task olusturur.Task otomatik olarak giris yapan kullaniciya atanir."""
    task = await service.create(task_in, user_id=current_user.id)

    return ApiResponse(success=True, data=task)


@tasks_router.get("/", response_model=ApiResponse[PaginatedResponse[TaskResponse]])
async def get_all_tasks(
    service: TaskServiceDep,
      current_user: CurrentUserDep,
      status: TaskStatus | None = None,
      priority: TaskPriority | None = None,
      search: str | None= None,
      page: int = Query(default=1, ge=1),
      page_size: int = Query(default=10, ge=1, le=100)
    ):
    """Giris yapan kullanicinin tum task'larini filtre ve sayfali olarak listeler."""
    filters= TaskFilter(status=status, priority=priority, search=search)
    pagination = PaginationParams(page=page,page_size=page_size)

    tasks, total = await service.get_all(
        user_id=current_user.id,
        filters=filters,
        pagination=pagination
    ) 

    total_pages = (total + page_size - 1) // page_size # Yukari yuvarlama

    paginated = PaginatedResponse(
        items=tasks,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages
    )

    return ApiResponse(success=True, data=paginated)


@tasks_router.get("/{task_id}", response_model=ApiResponse[TaskResponse])
async def get_task(task_id: int, service: TaskServiceDep, current_user: CurrentUserDep):
    """Giris yapan kullanicinin belirttigi task'i getirir."""
    task = await service.get_by_id(task_id, user_id=current_user.id)

    return ApiResponse(success=True, data=task)


@tasks_router.put("/{task_id}", response_model=ApiResponse[TaskResponse])
async def update_task(
    task_id: int,
    task_in: TaskUpdate,
    service: TaskServiceDep,
    current_user: CurrentUserDep,
):
    """Giris yapan kullanicinin belirttigi gorevi gunceller."""
    task = await service.update(task_id, task_in, user_id=current_user.id)

    return ApiResponse(success=True, data=task)


@tasks_router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(
    task_id: int, service: TaskServiceDep, current_user: CurrentUserDep
):
    """Giris yapan kullanicinin belirttigi gorevi siler."""
    await service.delete(task_id, user_id=current_user.id)

    return ApiResponse(success=True, data=True)
