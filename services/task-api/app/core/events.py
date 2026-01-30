"""
Task event publisher
Event'leri RabbitMQ'ya publish eden is mantigi.
"""
from datetime import datetime, UTC
from statistics import correlation
from app.core.correlation import get_correlation_id
from app.core.logging import get_logger
from app.core.messaging import RabbitMQClient,rabbitmq_client
from app.models.events import TaskEventType,TaskEvent
from app.core.dapr_pubsub import dapr_pubsub, TOPIC_NAME
logger = get_logger(__name__)

class TaskEventPublisher:
    """
    Task event'lerini Dapr Pub/Sub uzerinden publish eden class.
    Artik rabbiMQ'ya baglamiyoruz.
    Dapr sidecar'a HTTP ile event gonderiyoruz.
    Dapr, event'i RabbitMQ'ya (veya baska broker'a) iletiyor.
    
    1. Encapsulation: Event olusturma ve publish mantigi tek yerde
    2. Reusability: Tum service'ler ayni publisher'i kullanir
    3. Testability: Mock'lanarak test edilebilir
    4. Single Responsibility: Sadece event publishing ile ilgilenir
    """

    def __init__(self, topic: str = TOPIC_NAME):
        """
        Publisher instance' i olusturur.
        
        Args:
            client: RabbitMQ client (None ise global instance kullanilir.)
            Dependency inhection icin parametre olarak aliyoruz.
            Test'te mock client verebilmemizi sagliyor.
        """
        self._topic= topic

    async def publish_task_created(
        self,
        task_id: int,
        user_id: int,
        task_data: dict
    ) -> None:
        """
        TaskCreated event'i publish eder.

        Ne zaman kullanilir?
        - TaskService.create() basariyla tamamlandiginda

        Args:
            task_id:olusturulan task'in ID'si
            user_id: Task'i olusturan kullanici ID'si
            task_data: Task'in JSON-serializable verisi
        """
        event= TaskEvent(
            event_type=TaskEventType.CREATED,
            task_id=task_id,
            user_id=user_id,
            timestamp=datetime.now(UTC),
            correlation_id=get_correlation_id(),
            data=task_data
        )
        await self._publish(event)
        logger.info(
            f"Published TaskCreated event for tas {task_id}",
            extra={"correlation_id": event.correlation_id}
        )
    
    async def publish_task_updated(
        self,
        task_id: int,
        user_id: int,
        task_data: dict
    ) -> None:
        """
        TaskUpdated event'i publish eder.
        
        Args:
            task_id: Silinen task'in ID'si
            user_id: Task'i silen kullanici
            task_data: Task'in guncel verisi
        """
        event=TaskEvent(
            event_type=TaskEventType.UPDATED,
            task_id=task_id,
            user_id=user_id,
            timestamp=datetime.now(UTC),
            correlation_id=get_correlation_id(),
            data=task_data
        )
        await self._publish(event)
        logger.info(
            f"Published TaskUpdated event for task {task_id}",
            extra={"correlation_id":event.correlation_id}
        )
    async def publish_task_deleted(
        self,
        task_id: int,
        user_id: int,
    ) -> None:
        """
        TaskDeleted event'i publish eder.
        
        Args:
            task_id: Silinen task'in ID'si
            user_id: Task'i silen kullanici ID'si 
        """
        event = TaskEvent(
            event_type=TaskEventType.DELETED,
            task_id=task_id,
            user_id=user_id,
            timestamp=datetime.now(UTC),
            correlation_id=get_correlation_id(),
            data=None
        )
        await self._publish(event)
        logger.info(
            f"Published TaskDeleted event for task {task_id}",
            extra={"correlation_id":event.correlation_id}
        )
    
    async def publish_task_completed(
        self,
        task_id: int,
        user_id: int,
        task_data: dict
    )->None:
        """
        TaskCompleted event'i publish eder.

        Args:
            task_id:tamamlanan task'in ID'si
            user_id: Task'i tamamlayan kullanicinin ID'si
            task_data: Task'in son hali
        
       """
        event= TaskEvent(
            event_type=TaskEventType.COMPLETED,
            task_id=task_id,
            user_id=user_id,
            timestamp=datetime.now(UTC),
            correlation_id=get_correlation_id(),
            data=task_data
        )
        await self._publish(event)
        logger.info(
            f"Published TaskCompleted event for tas {task_id}",
            extra= {"correlation_id":event.correlation_id }
        )
    async def _publish(self, event: TaskEvent) -> None:
        """
        Event'i Dapr Pub/Sub'a gonderir.

        Args:
            event: Gonderilecek event
        
        """
        try:
            success= await dapr_pubsub.publish(
                topic=self._topic,
                data= event.to_dict()
            )
            if not success:
                logger.warning(
                    f"Event publish returned False: {event.event_type.value}",
                    extra={"correlation_id":event.correlation_id}
                )
        except Exception as e:
            #Event publish hatasi ana islemi etkilememeli
            logger.error(
                f"Failed to publish event {event.event_type.value}: {e}",
                extra={"correlation_id":event.correlation_id}
            )

# Global Instance
task_event_publisher = TaskEventPublisher()