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

    async def create(self, task_in: TaskCreate) -> TaskResponse:
        logger.info(f"Creating task: {task_in.title}")
        # pydantic modeli veritabani nesnesine donusturdugumuz asama
        new_task = TaskEntity(**task_in.model_dump())
        created_entity = await self.repo.create(new_task)

        return TaskResponse.model_validate(created_entity)

    async def get_all(self) -> list[TaskResponse]:
        logger.info("Fetching All Tasks")
        entities = await self.repo.get_all()

        return [TaskResponse.model_validate(e) for e in entities]

    async def get_by_id(self, task_id: int) -> TaskResponse:
        logger.info(f"Fetching task:{task_id}")

        entity = await self.repo.get_by_id(task_id)

        if not entity:
            raise TaskNotFoundException(task_id=task_id)

        return TaskResponse.model_validate(entity)

    async def update(self, task_id: int, task_in: TaskUpdate) -> TaskResponse:
        logger.info(f"Updating Task:{task_id}")

        entity = await self.repo.get_by_id(task_id)
        if not entity:
            raise TaskNotFoundException(task_id=task_id)

        update_data = task_in.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(entity, key, value)

        updated_entity = await self.repo.update(entity)

        return TaskResponse.model_validate(updated_entity)

    async def delete(self, task_id: int) -> None:
        logger.info(f"deleting task: {task_id}")
        entity = await self.repo.get_by_id(task_id)
        if not entity:
            raise TaskNotFoundException(task_id)
        await self.repo.delete(entity)
