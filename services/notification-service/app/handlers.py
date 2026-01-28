"""
Event handler'lar.
Her event tipi icin ayri handler fonksiyonu icerir.
"""
from argparse import Action
import asyncio
import logging
from readline import set_completion_display_matches_hook
from statistics import correlation
logger=logging.getLogger(__name__)

async def handle_task_created(event_data: dict) -> None:
    """
    TaskCreated event'ini handle eder.

    Args:
        event_data: Event verisi
    """
    task_id=event_data.get("task_id")
    task_data=event_data.get("data",{})
    correlation_id = event_data.get("correlation_id")

    logger.info(
        f"Handling TaskCreated: Task #{task_id} - '{task_data.get('title')}'",
        extra={"correlation_id":correlation_id}
    )

    # Simulated email sending
    await send_email_notification(task_data, correlation_id)

    # Simulated webhook
    await send_webhook_notification("task_created",task_data,correlation_id)

async def handle_task_updated(event_data: dict) -> None:
    """
    TaskUpdated event'ini handle eder.

    Args:
        event_data: Event verisi
    """
    task_id = event_data.get("task_id")
    task_data = event_data.get("data",{})
    correlation_id = event_data.get("correlation_id")

    logger.info(
        f"Handling TaskUpdated: Task #{task_id}",
        extra={"correlation_id":correlation_id}
    )

    await send_email_notification(task_data, correlation_id, action="updated")

async def handle_task_deleted(event_data: dict)-> None:
    """
    TaskDeleted event'ini handle eder.
    
    Args:
        event_data: Event verisi
    """
    task_id = event_data.get("task_id")
    correlation_id=event_data.get("correlation_id")

    logger.info(
        f"Handling TaskDeleted: Task #{task_id}",
        extra={"correlation_id":correlation_id}
    )

    await send_email_notification({"id":task_id},correlation_id, action="deleted")

async def handle_task_completed(event_data: dict)-> None:
    """
    TaskCompleted event'ini handle eder.
    
    Args:
        event_data: Event verisi
    """
    task_id = event_data.get("task_id")
    task_data = event_data.get("data",{})
    correlation_id = event_data.get("correlation_id")

    logger.info(
        f"Handling TaskCompleted: Task #{task_id}",
        extra={"correlation_id":correlation_id}
    )
    
    await send_email_notification(task_data,correlation_id,action="completed")
    await send_webhook_notification("task_completed", task_data,correlation_id)

# ------ NOTIFICATION HELPERS ------ #
async def send_email_notification(
    task_data: dict,
    correlation_id: str | None,
    action : str = "created"
) -> None:
    """
    Email bildirimi gonderir.(simulatif olarak gercegini ekleyecem ins)
    
    Args:
        task_data: Task verisi
        correlation_id: Request tracing ID
        action: Aksiyon tipi (created, updated, deleted, completed)
    """

    # Simulated email sending delay
    await asyncio.sleep(0.1)

    logger.info(
        f"EMAIL SENT: TASK{action} - {task_data.get('title'.'N/A')}",
        extra={"correlation_id":correlation_id}
    )

async def send_webhook_notification(
    event_type: str,
    task_data: dict,
    correlation_id: str | None
) -> None:
    """ 
    Webhook cagrisini simule eder.
    
    Args:
        event_type: Event tipi
        task_data: Task verisi
        correlation_id: Request tracing ID    
    """

    # Simulated webhook call delay
    await asyncio.sleep(0.05)

    logger.info(
        f"WEBHOOK CALLED: {event_type} - Task #{task_data.get('id')}",
        extra={"correlation_id":correlation_id}
    )