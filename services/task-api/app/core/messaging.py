"""
RabbitMQ messaging client.
Asenkron mesajlasma islemleri icin kullanilir.
Event publishing ve consuming islemlerini yonetir.
"""

import json
import logging
from types import coroutine
from typing import Any, Awaitable, Optional
from aio_pika import connect_robust, Message, ExchangeType
from aio_pika.abc import AbstractRobustConnection, AbstractRobustChannel, AbstractRobustExchange
from app.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

class RabbitMQClient:
    """
    RabbitMQ baglanti ve mesajlasma islemlerini yoneten client.

    Ozellikler:
        - Otomatik reconnect (robus connection)
        - Exchange ve queue yonetimi
        - JSON mesaj serialization
    """

    def __init__(self):
        """RabbitMQClient instance' i olusturur."""
        self.connection:AbstractRobusConnection | None = None
        self.channel: Optional[AbstractRobusChannel] = None
        self.exchange: Optional[AbstractRobusExchange] = None
    
    async def connect(self) -> None:
        """
        RabbitMQ'ya baglanti kurar.

        Robus connection kullanir - baglanti koparsa otomatik yeniden baglanir.

        Raises:
            Exception: Baglanti kurulamazsa 
        """
        try:
            # Robus connection kismi - otomatik reconnect
            self.connection = await connect_robust(settings.rabbitmq_url)

            # Channel olusturma kismi
            self.channel = await self.connection.channel()

            # Default exchange olusturma kismi (topic type - esnek routing)
            self.exchange = await self.channel.declare_exchange(
                "task_events",
                ExchangeType.TOPIC,
                durable=True # Broker restart'ta exchange kaybolmasin diye
            )

            logging.info(
                f"Connected to RabbitMQ at {settings.rabbitmq_host}:{settings.rabbitmq_port}"
            )
        except Exception as e:
            logger.error(f"RabbitMQ connection error: {e}")
            raise
    async def disconnect(self) -> None:
        """
        RabbitMQ baglantisini koparir.
        """
        if self.connection:
            await self.connection.close()
            logger.info(f"Disconnected from RabbitMQ")
    
    async def publish(
        self,
        routing_key: str,
        message: dict[str, Any],
        correlation_id: str | None = None
    ) -> None:
        """
        Exchange'e mesaj publish eder.

        Args:
            routing_key: Mesajin routing key'idir.(ornek:"task.created","task.updated")
            message: Gonderilecek mesaj (dict olarak, JSON'a cevrilir.)
            correlation_id: Request tracing icin correlation ID

        Raises:
            RuntimeError: Baglanti kurulmamissa
        """
        if not self.exchange:
            raise RuntimeError("RabbitMQ connection not established. Call connect() first.")
        
        # Correlation ID ekleme kismi
        if correlation_id:
            message["correlation_id"] = correlation_id
        
        # JSON'a cevir
        body = json.dumps(message,default=str).encode()

        # Mesaj olusturma kismi

        amqp_message = Message(
            body= body,
            content_type="application/json",
            correlation_id=correlation_id
        )

        # Publish kismi

        await self.exchange.publish(amqp_message, routing_key=routing_key)

        logger.debug(
            f"Published message to '{routing_key}'",
            extra={"correlation_id":correlation_id}
        )
    
    async def health_check() -> bool:
        """
        RabbitMQ baglanti durumunu kontrol eder.

        Returns:
            bool: baglanti saglikli ise True
        """
        try:
            if self.connection and not self.connection.is_closed:
                return True
        except Exception:
            return False

#Global Instance
rabbitmq_client = RabbitMQClient()