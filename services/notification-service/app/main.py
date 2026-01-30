"""
Notification Service - Dapr Subscriber.
Dapr Pub/Sub uzerinden event'leri dinler.
"""
from statistics import correlation
from fastapi import FastAPI, Request
from contextlib import asynccontextmanager
import logging
from app.handlers import(
    handle_task_completed,
    handle_task_created,
    handle_task_deleted,
    handle_task_updated
)
logging.basicConfig(
    level=logging.INFO,
    format = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app:FastAPI):
    logger.info("Notification Service starting...")
    yield
    logger.info("Notification Service shutting down...")

app = FastAPI(
    title="Notification Service",
    version = "1.0.0",
    lifespan=lifespan
)

# ---- DAPR SUBSCRIPTION ENDPOINT ----- #
@app.get("/dapr/subscribe")
async def subscribe():
    """
    Dapr'a hangi topicleri dinledigimizi bildirir.
    
    Dapr bu endpoint'i cagirarak subscription bilgisini alir.
    """
    subscriptions = [
    {
        "pubsubname":"taskpubsub",
        "topic":"task-events",
        "route":"/events/task"
    }
]
    logger.info(f"Dapr Subscription: {subscriptions}")
    return subscriptions

# ----- EVENT HANDLER ENDPOINT ----- #

@app.post("/events/task")
async def handle_task_event(request: Request):
    """
    Task event'lerini handle eder.

    Dapr, event geldiginde bu endpoint'i cagir.
    CloudEvents formatinda veri gelir.
    """
    try:
        # CloudEvents wrapper'dan data'yi al
        cloud_event = await request.json()

        #Dapr CloudEvents formatinda gonderir
        #data field'i icinde bizim event'imiz var
        event_data = cloud_event.get("data",cloud_event)

        event_type = event_data.get("event_type")
        correlation_id = event_data.get("correlation_id","-")

        logger.info(
            f"Received Event: {event_type}",
            extra= {"correlation_id": correlation_id}
        )

        #Route to handler
        if event_type == "task.created":
            await handle_task_created(event_data)
        elif event_type == "task.updated":
            await handle_task_updated(event_data)
        elif event_type == "task.deleted":
            await handle_task_deleted(event_data)
        elif event_type == "task.completed":
            await handle_task_completed(event_data)
        else:
            logger.warning(f"unkown event type: {event_type}")
        
        #Dapr'a basarili oldugunu bildir.
        return {"status":"SUCCESS"}
    except Exception as e:
        logger.error(f"Error handling event; {e}")

        #Dapr'a retry etmesini soyluyoruz.
        return {"status":"RETRY"}

# ----- HEALTH CHECK ----- #
@app.get("/health")
async def health():
    return {"status":"healthy"}