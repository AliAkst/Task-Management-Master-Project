from fastapi import APIRouter, status

from app.api.dependencies import TaskServiceDep
from app.models.common import ApiResponse
from app.models.task import TaskCreate, TaskResponse, TaskUpdate

tasks_router = APIRouter(prefix="/tasks", tags=["Tasks"])


@tasks_router.post(
    "/", response_model=ApiResponse[TaskResponse], status_code=status.HTTP_201_CREATED
)
async def create_task(task_in: TaskCreate, service: TaskServiceDep):
    task = await service.create(task_in)

    return ApiResponse(success=True, data=task)


@tasks_router.get("/", response_model=ApiResponse[list[TaskResponse]])
async def get_all_tasks(service: TaskServiceDep):
    tasks = await service.get_all()

    return ApiResponse(success=True, data=tasks)


@tasks_router.get("/{task_id}", response_model=ApiResponse[TaskResponse])
async def get_task(task_id: int, service: TaskServiceDep):
    task = await service.get_by_id(task_id)

    return ApiResponse(success=True, data=task)


@tasks_router.put("/{task_id}", response_model=ApiResponse[TaskResponse])
async def update_task(task_id: int, task_in: TaskUpdate, service: TaskServiceDep):
    task = await service.update(task_id, task_in)

    return ApiResponse(success=True, data=task)


@tasks_router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(task_id: int, service: TaskServiceDep):
    await service.delete(task_id)

    return ApiResponse(success=True, data=True)
