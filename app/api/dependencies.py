from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db_session
from app.services.task import TaskService


async def get_task_service(
    session: AsyncSession = Depends(get_db_session),
) -> TaskService:
    """Veritabani sessioni alir ve bu session ile calisan
    bir task service nesnesi uretir."""

    return TaskService(session)


TaskServiceDep = Annotated[TaskService, Depends(get_task_service)]
