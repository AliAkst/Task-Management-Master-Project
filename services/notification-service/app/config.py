"""
Notification Service Configuration
"""
import os
from dotenv import load_dotenv
load_dotenv()
class Settings:
    """Notification service ayarlari."""

    # RabbitMQ ayarlari
    rabbitmq_host: str = os.getenv("RABBITMQ_HOST","localhost")
    rabbitmq_port: int = int(os.getenv("RABBITMQ_PORT","5672"))
    rabbitmq_user: str = os.getenv("RABBITMQ_USER", "taskuser")
    rabbitmq_password: int = os.getenv("RABBITMQ_PASSWORD","taskpass")
    rabbitmq_vhost: str = os.getenv("RABBITMQ_VHOST","taskhost")

    @property
    def rabbitmq_url(self)-> str:
        """RabbitMQ connection URL."""
        return f"amqp://{self.rabbitmq_user}:{self.rabbitmq_password}@{self.rabbitmq_host}:{self.rabbitmq_port},{self.rabbitmq_vhost}"
    

    # Global Instance
    settings = Settings()