"""
Dapr Pub/Sub client.
Event'leri Dapr uzerinden publish etmek icin kullanilir.
"""

import httpx
from datetime import datetime, UTC
from typing import Any
from app.core.logging import get_logger
from app.core.correlation import get_correlation_id

logger = get_logger(__name__)

#Dapr sidecar URL
DAPR_HTTP_PORT = 3500

DAPR_BASE_URL = f"http://localhost:{DAPR_HTTP_PORT}"

# Pub,Sub component adi (pubsub.yaml'daki name)

PUBSUB_NAME = "taskpubsub"
TOPIC_NAME = "task-events"

class DaprPubSubClient:
    """
    Dapr Pub/Sub client.

    Event'leri dapr sidecar uzerinden publish eder.
    Dapr, event'i RabbitMQ'ya (veya baska broker'a) iletir.    
    """
    def __init__(self,pubsub_name: str = PUBSUB_NAME, timeout: float = 10.0):
        """
        DaprPubSubClient instance'i olusturur.

        Args:
            pubsub_name: Dapr pubsub component ado
            timeout: HTTP timeout (saniye)        
        """
        self._pubsub_name = pubsub_name
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None
    
    async def _get_client(self) -> httpx.AsyncClient:
        """
        Lazy initialization ile HTTP client dondurur.
        """
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=DAPR_BASE_URL,
                timeout = self._timeout
            )
        return self._client
    
    async def close(self)-> None:
        """
        HTTP client'i kapatir.
        """
        if self._client:
            await self._client.aclose()
            self._client = None
    
    async def publish(
        self,
        topic: str,
        data: dict[str,Any],
        metadata: dict[str, str] | None = None
    )->bool:
        """
        Event Publish eder.
        
        Args:
            topic: Topic adi (orn: "task-events")
            data: Event verisi
            metada: Opsiyonel metadata
        
        Returns:
            bool: Basarili ise True
        """
        client = await self._get_client()

        url = f"/v1.0/publish/{self._pubsub_name}/{topic}"

        # Correlation ID ekledigimiz kisim
        correlation_id = get_correlation_id()
        if correlation_id:
            data["correlation_id"] = correlation_id
        
        if "timestamp" not in data:
            data["timestamp"] = datetime.now(UTC).isoformat()
        
        headers = {}
        if metadata:
            # Dapr metadata header'lari
            for key, value in metadata.items():
                headers[f"metadata.{key}"] = value
        logger.info(
            f"Dapr publish: {topic} -> {data.get('event_type','unkown')}",
            extra={"correlation_id":correlation_id}
        )

        try:
            response = await client.post(url, json=data, headers=headers)
            response.raise_for_status()

            logger.debug(
                f"Dapr publish success: {topic}",
                extra={"correlation_id":correlation_id}
            )
            return True
        except httpx.HTTPStatusError as e:
            logger.error(
                f"Dapr publish error: {topic} -> {e}",
                extra={"correlation_id":correlation_id}
            )
            return False
        
# Global Instance
dapr_pubsub = DaprPubSubClient()