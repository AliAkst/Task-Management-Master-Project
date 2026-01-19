from fastapi import APIRouter, status

from app.api.dependencies import CurrentUserDep, TaskServiceDep
from app.models.common import ApiResponse
from app.models.task import TaskCreate, TaskResponse, TaskUpdate

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


@tasks_router.get("/", response_model=ApiResponse[list[TaskResponse]])
async def get_all_tasks(service: TaskServiceDep, current_user: CurrentUserDep):
    """Giris yapan kullanicinin tum task'larini listeler."""
    tasks = await service.get_all(user_id=current_user.id)

    return ApiResponse(success=True, data=tasks)


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
