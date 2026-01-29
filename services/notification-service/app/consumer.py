"""
RabbitMQ consumer with Dead Letter Queue support.
Event'leri dinler ve handlerlara yonlendirir.
Hata durumunda retry yapar, max retry asilirsa DLQ'ya gonderir.

"""

import asyncio
import json
import signal
import logging
from aio_pika import connect_robust, ExchangeType, Message
from aio_pika.abc import AbstractIncomingMessage
from app.config import settings
from app.handlers import (
    handle_task_created,
    handle_task_completed,
    handle_task_deleted,
    handle_task_updated
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(correlation_id)s | %(levelname)-8s | %(name)s | %(message)s |",
    datefmt="%Y-%m-%d %H:%M:%S"
)
# Correlation ID Filter
class CorrelationIdFilter(logging.Filter):
    def filter(self, record):
        if not hasattr(record, 'correlation_id'):
            record.correlation_id = "-"
        return True

logging.getLogger().addFilter(CorrelationIdFilter())

logger = logging.getLogger(__name__)

#Constants
MAX_RETRIES = 3
RETRY_HEADER = "x-retry-count"

# Graceful shutdown
shutdown_event = asyncio.Event()

def signal_handler(sig, frame):
    """
    graceful shutdown icin Signal handler 
    """
    logger.info("Shutdown isareti alindi, mevcut gorevler tamamlaniyor...")
    shutdown_event.set() # event flaglarini aktiflestiriyoruz.
signal.signal(signal.SIGINT, signal_handler) # Ctrl + C
signal.signal(signal.SIGTERM, signal_handler) # Docker stop/kill

def get_retry_count(message:AbstractIncomingMessage) -> int:
    """
    Mesajin retry sayisini dondurur.

    Args:
        message: RabbitMQ mesaji
    Returns:
        int: Retry sayisi (0 = ilk deneme)
    """
    headers= message.headers or {}
    return headers.get(RETRY_HEADER, 0)

async def process_message(
    message: AbstractIncomingMessage,
    channel,
    exchange,
    dlx_exchange    
) -> None:
    """
    Gelen mesaji isle.
    
    Args:
        message: RabbitMQ mesaji
    """
    retry_count= get_retry_count(message)
    correlation_id = "-"
    try:
        # Parse JSON
        body = message.body.decode()
        event_data = json.loads(body)

        event_type = event_data.get("event_type")
        correlation_id = event_data.get("correlation_id","-")

        logger.info(
            f"Received event: {event_type}",
            extra={"correlation_id":correlation_id}
        )

        # handler route ediyoruz yani yonlendiriyoruz bu kisimda
        if event_type == "task.created":
            await handle_task_created(event_data)
        elif event_type == "task.updated":
            await handle_task_updated(event_data)
        elif event_type == "task.deleted":
            await handle_task_deleted(event_data)
        elif event_type == "task.completed":
            await handle_task_completed(event_data)
        else:
            logger.warning(
                f"Unkown event type: {event_type}",
                extra={"correlation_id":correlation_id}
            )
        
        # Basarili - ACK
        await message.ack()
        logger.debug(
            f"Message processed successfully",
            extra={"correlation_id":correlation_id}
        )
    
    except Exception as e:
        logger.error(
            f"Mesajdaki hata isleniyor: {e}",
            extra={"correlation_id":correlation_id}
        )

        #Retry veya DLQ kararinin verildigi kisim
        if retry_count <MAX_RETRIES:
            #Retry: Mesaji tekrar kuyruga gonder (artirilmis retry count yaparak)
            await retry_message(message, channel,exchange, retry_count + 1)
            await message.ack()
            logger.warning(
                f"Message  requeued for retry ({retry_count + 1}/{MAX_RETRIES})",
                extra={"correlation_id":correlation_id}
            )
        else:
            #Max retry asildi demektir - DLQ'ya gonderdigimiz kisim
            await send_to_dlq(message,dlx_exchange,str(e))
            await message.ack() # Eski mesaji acknowladge edelim
            logger.error(
                f"Message sent to DLQ after {MAX_RETRIES} retries",
                extra={"correlation_id":correlation_id}
            )
async def retry_message(
    original_message: AbstractIncomingMessage,
    channel,
    exchange,
    retry_count: int
) -> None:
    """
    Mesaji retry icin tekrar kuyruga gonderir.
    
    Args:
        original_message: Orjinal mesaj
        channel:RabbitMQ channeli
        exchange: Ana exchange
        retry_count: yeni retry sayisi
    """
    # Yeni headers olustur
    headers = dict(original_message.headers or {})
    headers[RETRY_HEADER]= retry_count

    # Yeni mesaj olustur
    new_message = Message(
        body=original_message.body,
        headers=headers,
        content_type=original_message.content_type,
        correlation_id= original_message.correlation_id
    )

    # Ayni routing key ile tekrar publish et
    await exchange.publish(
        new_message,
        routing_key = original_message.routing_key or "task.unkown"
    )

async def send_to_dlq(
    message: AbstractIncomingMessage,
    dlx_exchange,
    error_reason: str
)-> None:
    """
    Mesaji Dead Letter Queue'ya gonderir.

    Args:
        message: Orjinal mesaj
        dlx_exchange: Dead letter exchange
        error_reason: Hata sebebi
    """
    # Headers'a hata bilgisi ekle
    headers = dict(message.headers or {})
    headers["x-death-reason"] = error_reason
    headers["x-original-routing-key"] = message.routing_key

    #DQL mesaji olustur
    dlq_message=Message(
        body=message.body,
        headers=headers,
        content_type=message.content_type,
        correlation_id=message.correlation_id
    )

    #DLQ'ya gonder
    await dlx_exchange.publish(
        dlq_message,
        routing_key="dead"
    )

async def start_consumer():
    """
    RabbitMQ consumer'i baslatir.
    """
    logger.info(f"Connecting to RabbitMQ at {settings.rabbitmq_host}:{settings.rabbitmq_port}")

    # Connect
    connection = await connect_robust(settings.rabbitmq_url)
    channel= await connection.channel()
    await channel.set_qos(prefetch_count= 10) #max 10 mesaji paralelde isle

    # ---MAIN EXCHANGE ---
    exchange = await channel.declare_exchange(
        "task_events",
        ExchangeType.TOPIC,
        durable=True
    )
    
    # ---DEAD LETTER EXCHANGE ---
    dlx_exchange = await channel.declare_exchange(
        "task_events.dlx",
        ExchangeType.DIRECT,
        durable=True
    )
    # ---DEAD LETTER QUEUE---
    dlq = await channel.declare_queue(
        "notifications.dead_letter",
        durable= True
    )
    await dlq.bind(dlx_exchange, routing_key="dead")  


    # ---MAIN QUEUE---
    queue = await channel.declare_queue(
        "notifications",
        durable= True
    )

    # Bind
    await queue.bind(exchange, routing_key = "task.*")
    logger.info(f"Consumer started, listenin on queue 'notifications'")
    logger.info(f"Bound to exchange 'task_events' with routing key 'task.*'")
    logger.info(f"Dead Letter Queue: 'notifications.dead_letter'")

    # Consume
    async with queue.iterator() as queue_iter:
        async for message in queue_iter:
            if shutdown_event.is_set():
                logger.info("Shutdown event set, stopping consumer...")
                break
        
            await process_message(message,channel,exchange,dlx_exchange)
    
    await connection.close()
    logger.info("Consumer stopped")

if __name__ =="__main__":
    asyncio.run(start_consumer())