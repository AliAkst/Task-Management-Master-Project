"""
Domain event publisher.
Event'leri dogrudan RabbitMQ'ya (aio-pika, topic exchange "task_events") publish eder.

Dapr kaldirildi: her servis icin ayri sidecar gerektiriyordu ve kisisel kullanimda
katma degeri dusuktu. Ayni RabbitMQ altyapisi aio-pika ile dogrudan kullaniliyor.
"""

from datetime import UTC, datetime
from typing import Any

from app.core.correlation import get_correlation_id
from app.core.logging import get_logger
from app.core.messaging import RabbitMQClient, rabbitmq_client
from app.models.events import TaskEvent, TaskEventType

logger = get_logger(__name__)


class DomainEventPublisher:
    """
    Tum domain event'leri (task.*, board.*, session.*, review.*) icin ortak
    publisher.

    - Routing key = event tipi (orn. "task.completed"); consumer'lar pattern
      ile dinler.
    - RabbitMQ bagli degilse event atlanir; event publish hatasi ana islemi asla bozmaz.
    """

    def __init__(self, client: RabbitMQClient | None = None):
        # Dependency injection: testte mock client verilebilir
        self._client = client or rabbitmq_client

    @property
    def is_available(self) -> bool:
        return self._client.exchange is not None

    async def publish(self, routing_key: str, payload: dict[str, Any]) -> bool:
        """
        Event'i publish eder.

        Returns:
            bool: Event gonderildiyse True
        """
        correlation_id = payload.get("correlation_id") or get_correlation_id()
        if not self.is_available:
            logger.debug(
                f"RabbitMQ not connected, skipping event {routing_key}",
                extra={"correlation_id": correlation_id},
            )
            return False
        try:
            await self._client.publish(
                routing_key=routing_key,
                message=payload,
                correlation_id=correlation_id,
            )
            return True
        except Exception as e:
            logger.error(
                f"Failed to publish event {routing_key}: {e}",
                extra={"correlation_id": correlation_id},
            )
            return False


class TaskEventPublisher:
    """Task event'leri icin kolaylik metotlari (DomainEventPublisher uzerine)."""

    def __init__(self, publisher: DomainEventPublisher | None = None):
        self._publisher = publisher or domain_event_publisher

    async def _publish(
        self,
        event_type: TaskEventType,
        task_id: int,
        user_id: int,
        task_data: dict | None,
    ) -> None:
        event = TaskEvent(
            event_type=event_type,
            task_id=task_id,
            user_id=user_id,
            timestamp=datetime.now(UTC),
            correlation_id=get_correlation_id(),
            data=task_data,
        )
        if await self._publisher.publish(event.event_type.value, event.to_dict()):
            logger.info(
                f"Published {event.event_type.value} event for task {task_id}",
                extra={"correlation_id": event.correlation_id},
            )

    async def publish_task_created(
        self, task_id: int, user_id: int, task_data: dict
    ) -> None:
        await self._publish(TaskEventType.CREATED, task_id, user_id, task_data)

    async def publish_task_updated(
        self, task_id: int, user_id: int, task_data: dict
    ) -> None:
        await self._publish(TaskEventType.UPDATED, task_id, user_id, task_data)

    async def publish_task_deleted(self, task_id: int, user_id: int) -> None:
        await self._publish(TaskEventType.DELETED, task_id, user_id, None)

    async def publish_task_completed(
        self, task_id: int, user_id: int, task_data: dict
    ) -> None:
        await self._publish(TaskEventType.COMPLETED, task_id, user_id, task_data)


# Global Instance'lar
domain_event_publisher = DomainEventPublisher()
task_event_publisher = TaskEventPublisher()
