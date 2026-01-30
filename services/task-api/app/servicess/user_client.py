"""
User Service client
User service'i Dapr uzerinden cagirmak icin wrapper.
"""
from venv import logger
from app.core.dapr_client import dapr_client, DaprInvocationError
from app.core.logging import get_logger

logger = get_logger(__name__)
USER_SERVICE_APP_ID = "user-service"
async def get_user_by_id(user_id: int)-> dict | None:
    """
    User Service'den kullanici bilgisini getirir.

    Args:
        user_id: Kullanici ID'si
    Returns:
        dict: Kullanici bilgisi veya None
    """
    try:
        user = await dapr_client.get(
            app_id=USER_SERVICE_APP_ID,
            method=f"api/v1/users/{user_id}"
        )
        return user
    except DaprInvocationError as e:
        if e.status_code == 404:
            logger.warning(f"User Not found: {user_id}")
            return None
        logger.error(f"Failed to get user {user_id}: {e}")
        raise

async def get_user_email(user_id: int) -> str | None:
    """
    Kullanicinin email adresini getirir.

    Args:
        user_id: Kullanici ID'si
    Returns:
        str: Email adresi veya None
    """
    user= await get_user_by_id(user_id)
    return user.get("email") if user else None