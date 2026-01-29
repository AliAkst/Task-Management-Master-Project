"""
DLQ monitoring utiilities
"""
import asyncio
import logging
from aio_pika import connect_robust
from app.config import settings
from aio_pika import Message

logger = logging.getLogger(__name__)

async def get_dlq_message_count() -> int:
    """
    DLQ'daki mesaj sayisini dondurur.
    
    Returns:
        int: mesaj sayisi
    """
    try:
        connection= await connect_robust(settings.rabbitmq_url)
        channel= await connection.channel()

        #Queue'yu passive declare edelim (sadece bilgi almak icin)
        queue = await channel.declare_queue(
            "notifications.dead_letter",
            durable=True,
            passive=True # saece bilgi al, olusturma diyoruz
        )

        count = queue.declaration_result.message_count
        await connection.close()
        
        return count
    except Exception as e:
        logger.error(f"Error getting DLQ count: {e}")
        return -1

async def reprocess_dlq_messages(limit: int = 10) -> int:
    """
    DLQ'daki mesajlari ana kuyruga geri gonderir.

    Args:
        limit: Maksimum islenecek mesaj sayisi
 
    Returns:
        int Geri gonderilen mesaj sayisi
    """
    try:
        connection = await connect_robust(settings.rabbitmq_url)
        channel= await connection.channel()

        # Exchanges
        exchange = await channel.declare_exchange(
            "task_events",
            passive=True
        )

        # DLQ
        dlq = await declare_queue(
            "notifications.dead_letter",
            durable=True
        )
        reprocessed = 0

        for _ in range(limit):
            message = await dlq.get(no_ack = False)
            if message is None:
                break
            
            # Orjinal routing key' i aliyoruz
            headers=message.headers or {}
            original_routing_key = headers.get("x-original-routing-key","task.unkown")

            # Retry count'u sifirla
            new_headers = {k: v for k, v in headers.items() if k != "x-retry-count"}
            new_headers["x-reprocessed-from-dlq"] = True

            # Ana exchange'e gonder
            new_message=Message(
                body=message.body,
                headers=new_headers,
                content_type=message.content_type
            )
            await exchange.publish(new_message,routing_key=original_routing_key)
            await message.ack()
            reprocessed += 1

            logger.info(f"Reprocessed message from DLQ:{original_routing_key}")
        
        await connection.close()
        return reprocessed
    
    except Exception as e:
        logger.error(f"Error reprocessing DLQ: {e}")
        return 0

if __name__ == "__main__":
    # CLI tool olarak kullanilabilir
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "count":
        count = asyncio.run(get_dlq_message_count())
        print(f"DLQ message count: {count}")
    elif len (sys.argv) > 1 and sys.argv[1] == "reprocess":
        limit = int(sys.argv[2]) if len(sys.argv) > 2 else 10
        count = asyncio.run(reprocess_dlq_messages(limit))
        print(f"Reprocessed {count} messages from DLQ")
    else:
        print(f"Usage: python -m app.monitor [count|reprocess [limit]]")