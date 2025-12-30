from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status

from app.models.common import ApiResponse
from app.models.task import TaskCreate, TaskResponse, TaskUpdate

router = APIRouter(prefix="/tasks", tags=["Tasks"])

tasks_db: dict[int, dict] = {}
task_id_counter = 0


@router.post(
    "/", response_model=ApiResponse[TaskResponse], status_code=status.HTTP_201_CREATED
)
def create_task(task_in: TaskCreate):
    global task_id_counter
    task_id_counter += 1
    now = datetime.now(UTC)
    new_task = {
        "id": task_id_counter,
        **task_in.model_dump(),
        "created_at": now,
        "updated_at": now,
    }
    tasks_db[task_id_counter] = new_task
    return ApiResponse(success=True, data=new_task)


@router.get("/", response_model=ApiResponse[list[TaskResponse]])
def get_all_tasks():
    return ApiResponse(success=True, data=list(tasks_db.values()))


@router.get("/{task_id}", response_model=ApiResponse[TaskResponse])
def get_task(task_id: int):
    if task_id not in tasks_db:
        raise HTTPException(status_code=404, detail=f"Task {task_id} bulunamadı!")
    return ApiResponse(success=True, data=tasks_db[task_id])


@router.put("/{task_id}", response_model=ApiResponse[TaskResponse])
def update_task(task_id: int, task_in: TaskUpdate):
    if task_id not in tasks_db:
        raise HTTPException(status_code=404, detail="Task bulunamadı.")
    current_data = tasks_db[task_id]
    update_data = task_in.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        current_data[key] = value
    current_data["updated_at"] = datetime.now(UTC)
    tasks_db[task_id] = current_data
    return ApiResponse(success=True, data=current_data)


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(task_id: int):
    if task_id not in tasks_db:
        raise HTTPException(status_code=404, detail="Task bulunamadı.")
    del tasks_db[task_id]
    return
