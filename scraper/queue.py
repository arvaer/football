"""RabbitMQ queue management with aio-pika."""

import asyncio
import json
from typing import Callable, Optional, Any
import aio_pika
from aio_pika import Message, ExchangeType
from aio_pika.abc import AbstractIncomingMessage
import structlog

from scraper.config import settings
from scraper.models import ScrapingTask, RepairTask

logger = structlog.get_logger()

# Flag to track if we're shutting down
_is_shutting_down = False


class QueueManager:
    """Manages RabbitMQ connections and queue operations."""
    
    def __init__(self):
        self.connection: Optional[aio_pika.RobustConnection] = None
        self.channel: Optional[aio_pika.Channel] = None
        self.queues: dict[str, aio_pika.Queue] = {}
        
    async def connect(self):
        """Establish connection to RabbitMQ."""
        logger.info("connecting_to_rabbitmq", url=settings.rabbitmq.url)
        
        try:
            self.connection = await aio_pika.connect_robust(
                settings.rabbitmq.url,
                timeout=10,
            )
            
            self.channel = await self.connection.channel()
            await self.channel.set_qos(prefetch_count=settings.workers.prefetch_count)
            
            logger.info("rabbitmq_connected")
        except Exception as e:
            logger.error("rabbitmq_connection_failed", error=str(e), exc_info=True)
            raise
        
    async def declare_queues(self):
        """Declare all required queues with priority support."""
        queue_names = [
            settings.queues.discovery_queue,
            settings.queues.extraction_queue,
            settings.queues.repair_queue,
        ]
        
        for queue_name in queue_names:
            queue = await self.channel.declare_queue(
                queue_name,
                durable=True,
                arguments={
                    "x-max-priority": settings.queues.max_priority,
                }
            )
            self.queues[queue_name] = queue
            logger.info("queue_declared", queue=queue_name)
            
    async def publish_task(
        self,
        queue_name: str,
        task: ScrapingTask | RepairTask,
        priority: Optional[int] = None,
    ):
        """Publish a task to a queue."""
        if priority is None:
            priority = task.priority if isinstance(task, ScrapingTask) else 5
            
        message_body = task.model_dump_json().encode()
        
        message = Message(
            body=message_body,
            priority=priority,
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            content_type="application/json",
        )
        
        await self.channel.default_exchange.publish(
            message,
            routing_key=queue_name,
        )
        
        logger.debug(
            "task_published",
            queue=queue_name,
            url=task.url,
            priority=priority,
        )
        
    async def consume_tasks(
        self,
        queue_name: str,
        callback: Callable[[dict[str, Any]], Any],
        consumer_tag: Optional[str] = None,
    ):
        """Consume tasks from a queue."""
        queue = self.queues.get(queue_name)
        if not queue:
            raise ValueError(f"Queue {queue_name} not declared")
            
        async def process_message(message: AbstractIncomingMessage):
            try:
                task_data = json.loads(message.body.decode())
                logger.debug(
                    "processing_task",
                    queue=queue_name,
                    url=task_data.get("url"),
                )
                
                await callback(task_data)
                
                logger.debug(
                    "task_completed",
                    queue=queue_name,
                    url=task_data.get("url"),
                )
                
                # Ack the message after successful processing
                try:
                    await message.ack()
                except asyncio.CancelledError:
                    # During shutdown, don't ack - let the message be redelivered
                    if not _is_shutting_down:
                        raise
                        
            except asyncio.CancelledError:
                # Task was cancelled during processing - message will be redelivered
                if not _is_shutting_down:
                    logger.debug("task_cancelled", queue=queue_name)
                # Don't reject/ack - just let the connection close and requeue
                    
            except Exception as e:
                logger.error(
                    "task_processing_error",
                    queue=queue_name,
                    error=str(e),
                    exc_info=True,
                )
                # Reject and requeue the message on error
                try:
                    await message.reject(requeue=True)
                except asyncio.CancelledError:
                    # During shutdown, ignore rejection errors
                    if not _is_shutting_down:
                        raise
                except Exception:
                    # Suppress rejection errors during shutdown
                    pass
                    
        consumer = await queue.consume(process_message, consumer_tag=consumer_tag, no_ack=False)
        logger.info("consumer_started", queue=queue_name, consumer_tag=consumer_tag)
        
        # Keep the consumer alive by waiting indefinitely
        # The consumer processes messages in the background via the callback
        try:
            await asyncio.Event().wait()  # Wait forever until cancelled
        except asyncio.CancelledError:
            logger.info("consumer_cancelled", queue=queue_name, consumer_tag=consumer_tag)
            await consumer.cancel()
        finally:
            logger.info("consumer_cleanup", queue=queue_name, consumer_tag=consumer_tag)
        
    async def close(self):
        """Close connection to RabbitMQ."""
        global _is_shutting_down
        _is_shutting_down = True
        
        if self.connection:
            try:
                await self.connection.close()
                logger.info("rabbitmq_disconnected")
            except Exception as e:
                # Suppress errors during shutdown - connection may already be closed
                logger.debug("error_closing_connection", error=str(e))


# Global queue manager instance
_queue_manager: Optional[QueueManager] = None


async def get_queue_manager() -> QueueManager:
    """Get or create the global queue manager."""
    global _queue_manager
    
    if _queue_manager is None:
        _queue_manager = QueueManager()
        await _queue_manager.connect()
        await _queue_manager.declare_queues()
        
    return _queue_manager


async def publish_discovery_task(task: ScrapingTask):
    """Convenience function to publish discovery task."""
    qm = await get_queue_manager()
    await qm.publish_task(settings.queues.discovery_queue, task)


async def publish_extraction_task(task: ScrapingTask):
    """Convenience function to publish extraction task."""
    qm = await get_queue_manager()
    await qm.publish_task(settings.queues.extraction_queue, task)


async def publish_repair_task(task: RepairTask):
    """Convenience function to publish repair task."""
    qm = await get_queue_manager()
    await qm.publish_task(settings.queues.repair_queue, task, priority=8)
