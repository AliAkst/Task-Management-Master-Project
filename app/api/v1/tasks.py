from fastapi import APIRouter, HTTPException, status
from datetime import datetime, timezone
from app.models.task import TaskCreate, TaskPriority, TaskResponse, TaskStatus, TaskUpdate
from app.models.common import ApiResponse, ErrorDetail

router = APIRouter(prefix="/tasks", tags=["Tasks"])

# Geçici Hafıza(Cache)
tasks_db: dict[int, dict] = {}
task_id_counter = 0

@router.post("/",response_model=ApiResponse[TaskResponse], status_code=status.HTTP_201_CREATED)
def create_task(task_in : TaskCreate):
    global task_id_counter
    task_id_counter += 1

    now = datetime.now(timezone.utc)

    # Gelen veriyi dict'e cevirip uzerine ekleme yapiyoruz
    new_task = {
        "id" : task_id_counter,
        **task_in.model_dump(),
        "created_at" : now,
        "updated_at" : now
    }

    tasks_db[task_id_counter] = new_task

    return ApiResponse(success=True, data = new_task)

@router.get("/",response_model=ApiResponse[list[TaskResponse]])
def get_all_task():
    all_tasks = list(tasks_db.values())

    return ApiResponse(success=True, data=all_tasks)

@router.get("/{task_id}",response_model=ApiResponse[TaskResponse])
def get_task (task_id : int):
    if task_id not in tasks_db:
        raise HTTPException(status_code=404, detail=f"Task {task_id} bulunamadi!")
    
    return ApiResponse(success=True, data=tasks_db[task_id])

@router.delete("/{task_id}",status_code=status.HTTP_204_NO_CONTENT)
def delete_task(task_id : int):
    if task_id not in tasks_db:
        raise HTTPException(status_code=404, detail="Silinecek Gorev Bulunamadi.")
    
    del tasks_db[task_id]
    return

@router.put("/{task_id}", response_model=ApiResponse[TaskResponse])
def update_task(task_id : int, task_in: TaskUpdate)
    
    if task_id not in tasks_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,detail=f"ID'si{task_id} olan bir gorev bulunamadi."
        )
    
    # mevcut veriyi cek
    current_task_data = tasks_db[task_id]

    # akilli guncelleme
    update_data = task_in.model_dump(exclude_unset=True)

    # Dongu ile sadece gelen alanlari degistirme
    for key, value in update_data.items():
        current_task_data[key] = value
    
    # guncelleme tarihini simdi yap
    current_task_data["updated_at"] = datetime.now(timezone.utc)

    # Guncellenmis halini hafizaya yazalim.
    tasks_db[task_id] = current_task_data

    return ApiResponse(success=True, data=current_task_data)
