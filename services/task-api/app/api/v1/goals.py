"""Hedef endpoint'leri."""

from fastapi import APIRouter, Response, status

from app.api.dependencies import CurrentUserDep, GoalServiceDep
from app.db.entities.goal import GoalStatus
from app.models.common import ApiResponse
from app.services.goal import GoalCreate, GoalResponse, GoalUpdate

goals_router = APIRouter(prefix="/goals", tags=["Goals"])


@goals_router.get("", response_model=ApiResponse[list[GoalResponse]])
async def list_goals(
    service: GoalServiceDep, user: CurrentUserDep, status: GoalStatus | None = None
):
    return ApiResponse(success=True, data=await service.list(user.id, status))


@goals_router.post(
    "", response_model=ApiResponse[GoalResponse], status_code=status.HTTP_201_CREATED
)
async def create_goal(data: GoalCreate, service: GoalServiceDep, user: CurrentUserDep):
    return ApiResponse(success=True, data=await service.create(user.id, data))


@goals_router.patch("/{goal_id}", response_model=ApiResponse[GoalResponse])
async def update_goal(
    goal_id: int, data: GoalUpdate, service: GoalServiceDep, user: CurrentUserDep
):
    return ApiResponse(success=True, data=await service.update(goal_id, user.id, data))


@goals_router.delete("/{goal_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_goal(goal_id: int, service: GoalServiceDep, user: CurrentUserDep):
    await service.delete(goal_id, user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
