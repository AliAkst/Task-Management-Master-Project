
# --- CACHE IMPORTLARI ---
from app.core.cache import redis_cache
from app.core.cache_keys import (
    get_task_detail_cache_key,
    get_task_list_cache_key,
    get_task_user_pattern,
)
from app.core.exceptions import TaskNotFoundException
from app.core.logging import get_logger
from app.db.entities import TaskEntity
from app.db.repositories.specifications import (
    PaginationSpecification,
    Specification,
    TaskPrioritySpecification,
    TaskSearchSpecification,
    TaskStatusSpecification,
    TaskUserSpecification,
)

#--- UNIT OF PATTERN IMPORTLARI
from app.db.unit_of_work import TaskUnitOfWork
from app.models.common import PaginationParams
from app.models.task import TaskCreate, TaskFilter, TaskResponse, TaskUpdate

logger = get_logger(__name__)


class TaskService:
    def __init__(self, uow: TaskUnitOfWork):
        self.uow = uow

    async def create(self, task_in: TaskCreate, user_id: int) -> TaskResponse:
        """Yeni task olusturur ve user_id'yi otomatik atar"""
        logger.info(f"Creating task for user{user_id}: {task_in.title}")
        # pydantic modeli veritabani nesnesine donusturdugumuz asama
        new_task = TaskEntity(**task_in.model_dump(), user_id=user_id)
        created_task = await self.uow.tasks.create(new_task)
        await self.uow.commit()
        # ---CACHE INVALIDATION---
        await redis_cache.delete_pattern(get_task_user_pattern(user_id))

        return TaskResponse.model_validate(created_task)

    async def get_all(
            self,
              user_id: int,
              filters:TaskFilter,
              pagination:PaginationParams | None = None
              ) -> tuple[list[TaskResponse],int]:
        """Sadece kullaniciya ait filtrelenmis ve sayfalanmis tasklari(cache'li) getirir."""
        logger.info(f"Fetching All Tasks for user {user_id}")

        # ---Cache KEY olusturalim.
        cache_key = get_task_list_cache_key(
            user_id=user_id,
            status=filters.status.value if filters.status else None,
            priority=filters.priority.value if filters.priority else None,
            search=filters.search,
            page=pagination.page if pagination else 1
        )

        # --- CACHE'den denetelim
        cached_data = await redis_cache.get(cache_key)
        if cached_data:
            logger.debug(f"Cache HIT for key:{cache_key}")
            items= [TaskResponse.model_validate(item) for item in cached_data["items"]]
            return items, cached_data["total"]
        logger.debug(f"Cache MISS for key: {cache_key}")

        # --- DB'DEN CEK
        specs:list[Specification] = [TaskUserSpecification(user_id)]
        
        if filters:
            if filters.status:
                specs.append(TaskStatusSpecification(filters.status))
            if filters.priority:
                specs.append(TaskPrioritySpecification(filters.priority))
            if filters.search:
                specs.append(TaskSearchSpecification(filters.search))
        
        #toplam sayiyi aliyoruz.
        total = await self.uow.tasks.count(*specs)

        if pagination:
            specs.append(PaginationSpecification(pagination.page, pagination.page_size))
        
        entities = await self.uow.tasks.find(*specs)

        task_responses = [TaskResponse.model_validate(e) for e in entities]

        #---cache'e kaydedelim.
        cached_data = {
            "items": [t.model_dump() for t in task_responses],  # ✅ Mevcut listeyi kullan
            "total": total
        }
        await redis_cache.set(cache_key,cached_data)

        return task_responses, total

    async def get_by_id(self, task_id: int, user_id: int) -> TaskResponse:
        """Sadece kullanicinin kendisine ait belirli bir taski getirir"""
        logger.info(f"Fetching task for user {user_id} : {task_id}")
        
        #1-Cache key olusturalim
        cache_key = get_task_detail_cache_key(
            user_id=user_id,
            task_id=task_id
        )
        #2-Cache den getirmeyi deneyelim once
        cached_data = await redis_cache.get(cache_key)
        if cached_data:
            logger.debug(f"Cache HIT for task {task_id}")
            return TaskResponse.model_validate(cached_data)
        #3-DB'DEN CEKELIM.
        entity = await self.uow.tasks.get_by_id(task_id)

        if not entity:
            raise TaskNotFoundException(task_id=task_id)

        # sahiplik kontrolu yapiyoruz bu task bu kullaniciya mi ait
        if entity.user_id != user_id:
            logger.warning(f"User {user_id} tried to access task {task_id}")
            raise TaskNotFoundException(task_id=task_id)
        
        valid_data = TaskResponse.model_validate(entity).model_dump()
        await redis_cache.set(cache_key,valid_data)

        return TaskResponse.model_validate(entity)

    async def update(
        self, task_id: int, task_in: TaskUpdate, user_id: int
    ) -> TaskResponse:
        """Sadece kullanicinin kendisine ait taski gunceller."""
        logger.info(f"Updating Task for user {user_id} :{task_id}")

        entity = await self.uow.tasks.get_by_id(task_id)

        if not entity:
            raise TaskNotFoundException(task_id=task_id)

        if entity.user_id != user_id:
            logger.warning(f"User {user_id} tried to access task {task_id}")
            raise TaskNotFoundException(task_id=task_id)

        update_data = task_in.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(entity, key, value)

        updated_entity = await self.uow.tasks.update(entity)
        await self.uow.commit()
        await redis_cache.delete_pattern(get_task_user_pattern(user_id))
        return TaskResponse.model_validate(updated_entity)

    async def delete(self, task_id: int, user_id: int) -> None:
        """Sadece kullanicinin kendisine ait taski silmesini saglar."""
        logger.info(f"deleting task for user {user_id} : {task_id}")
        entity = await self.uow.tasks.get_by_id(task_id)

        if not entity:
            raise TaskNotFoundException(task_id)

        if entity.user_id != user_id:
            logger.warning(f"User {user_id} tried to access task {task_id}")
            raise TaskNotFoundException(task_id=task_id)

        await self.uow.tasks.delete(entity)
        await self.uow.commit()
        await redis_cache.delete_pattern(get_task_user_pattern(user_id))