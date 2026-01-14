from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import TaskNotFoundException
from app.core.logging import get_logger
from app.db.entities import TaskEntity
from app.db.repositories.task import TaskRepository
from app.models.task import TaskCreate, TaskResponse, TaskUpdate

logger = get_logger(__name__)


class TaskService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = TaskRepository(session)

    async def create(self, task_in: TaskCreate, user_id: int) -> TaskResponse:
        """Yeni task olusturur ve user_id'yi otomatik atar"""
        logger.info(f"Creating task for user{user_id}: {task_in.title}")
        # pydantic modeli veritabani nesnesine donusturdugumuz asama
        new_task = TaskEntity(**task_in.model_dump(), user_id=user_id)
        created_entity = await self.repo.create(new_task)

        return TaskResponse.model_validate(created_entity)

    async def get_all(self, user_id: int) -> list[TaskResponse]:
        """Sadece kullaniciya ait tasklari getirir."""
        logger.info(f"Fetching All Tasks for user {user_id}")
        entities = await self.repo.get_all_by_users(user_id)

        return [TaskResponse.model_validate(e) for e in entities]

    async def get_by_id(self, task_id: int, user_id: int) -> TaskResponse:
        """Sadece kullanicinin kendisine ait belirli bir taski getirir"""
        logger.info(f"Fetching task for user {user_id} : {task_id}")

        entity = await self.repo.get_by_id(task_id)

        if not entity:
            raise TaskNotFoundException(task_id=task_id)

        # sahiplik kontrolu yapiyoruz bu task bu kullaniciya mi ait
        if entity.user_id != user_id:
            logger.warning(f"User {user_id} tried to access task {task_id}")
            raise TaskNotFoundException(task_id=task_id)

        return TaskResponse.model_validate(entity)

    async def update(
        self, task_id: int, task_in: TaskUpdate, user_id: int
    ) -> TaskResponse:
        """Sadece kullanicinin kendisine ait taski gunceller."""
        logger.info(f"Updating Task for user {user_id} :{task_id}")

        entity = await self.repo.get_by_id(task_id)

        if not entity:
            raise TaskNotFoundException(task_id=task_id)

        if entity.user_id != user_id:
            logger.warning(f"User {user_id} tried to access task {task_id}")
            raise TaskNotFoundException(task_id=task_id)

        update_data = task_in.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(entity, key, value)

        updated_entity = await self.repo.update(entity)

        return TaskResponse.model_validate(updated_entity)

    async def delete(self, task_id: int, user_id: int) -> None:
        """Sadece kullanicinin kendisine ait taski silmesini saglar."""
        logger.info(f"deleting task for user {user_id} : {task_id}")
        entity = await self.repo.get_by_id(task_id)

        if not entity:
            raise TaskNotFoundException(task_id)

        if entity.user_id != user_id:
            logger.warning(f"User {user_id} tried to access task {task_id}")
            raise TaskNotFoundException(task_id=task_id)

        await self.repo.delete(entity)
