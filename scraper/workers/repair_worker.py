"""Repair worker - uses LLM to fix failed selectors."""

import asyncio
import json
import logging
from typing import Dict, Any
import structlog

from scraper.config import settings
from scraper.models import RepairTask, ScrapingTask
from scraper.queue import get_queue_manager, publish_extraction_task
from scraper.llm_client import get_llm_client

logger = structlog.get_logger()


class RepairAgent:
    """Agent for repairing failed extractions."""
    
    def __init__(self):
        self.llm = get_llm_client()
        
    async def repair_selectors(self, repair_task: RepairTask) -> bool:
        """Attempt to repair selectors and retry extraction."""
        logger.info(
            "attempting_repair",
            url=repair_task.url,
            page_type=repair_task.page_type,
        )
        
        try:
            # Ask LLM to suggest new selectors
            fields = ["player_name", "club_name", "fee", "date", "from_club", "to_club"]
            
            new_selectors = await self.llm.repair_selectors(
                html_snippet=repair_task.html_snippet,
                failed_selectors=repair_task.failed_selectors,
                fields_to_extract=fields,
            )
            
            logger.info(
                "selectors_generated",
                url=repair_task.url,
                new_selectors=new_selectors,
            )
            
            # Create new extraction task with updated metadata
            retry_task = ScrapingTask(
                url=repair_task.original_task.url,
                page_type=repair_task.original_task.page_type,
                priority=repair_task.original_task.priority,
                metadata={
                    **repair_task.original_task.metadata,
                    "repaired": True,
                    "suggested_selectors": new_selectors,
                },
                retry_count=repair_task.original_task.retry_count + 1,
            )
            
            # Send back to extraction queue
            await publish_extraction_task(retry_task)
            
            logger.info("repair_completed", url=repair_task.url)
            return True
            
        except Exception as e:
            logger.error(
                "repair_failed",
                url=repair_task.url,
                error=str(e),
                exc_info=True,
            )
            return False
            
    async def process_task(self, task_data: Dict[str, Any]):
        """Process a repair task."""
        task = RepairTask(**task_data)
        
        logger.info("processing_repair_task", url=task.url)
        
        # Attempt repair
        await self.repair_selectors(task)


async def run_repair_worker(worker_id: int):
    """Run repair worker process."""
    logger.info("repair_worker_starting", worker_id=worker_id)
    
    agent = RepairAgent()
    
    try:
        qm = await get_queue_manager()
        
        # Start multiple concurrent consumers
        tasks = []
        for i in range(settings.workers.concurrent_consumers):
            consumer_tag = f"repair_worker_{worker_id}_consumer_{i}"
            task = asyncio.create_task(
                qm.consume_tasks(
                    settings.queues.repair_queue,
                    agent.process_task,
                    consumer_tag=consumer_tag,
                )
            )
            tasks.append(task)
            
        # Wait for all consumers
        await asyncio.gather(*tasks)
        
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("repair_worker_stopping", worker_id=worker_id)


if __name__ == "__main__":
    import sys
    worker_id = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    
    # Configure structlog
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    )
    
    asyncio.run(run_repair_worker(worker_id))
