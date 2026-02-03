"""Main orchestrator - spawns and manages worker processes."""

import argparse
import asyncio
import logging
import multiprocessing
import signal
import sys
from pathlib import Path
import structlog

from scraper.config import settings
from scraper.models import ScrapingTask, PageType, TaskPriority
from scraper.queue import get_queue_manager, publish_discovery_task


logger = structlog.get_logger()


def configure_logging():
    """Configure structured logging."""
    log_dir = Path(settings.storage.logs_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    
    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.dev.ConsoleRenderer(),  # Print to console for visibility
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


async def seed_initial_tasks():
    """Seed the discovery queue with initial URLs."""
    logger.info("seeding_initial_tasks")
    
    qm = await get_queue_manager()
    
    for url in settings.transfermarkt.seeds:
        task = ScrapingTask(
            url=url,
            page_type=PageType.LEAGUE_CLUBS,
            priority=TaskPriority.CRITICAL,
            metadata={"seed": True},
        )
        
        await qm.publish_task(
            settings.queues.discovery_queue,
            task,
            priority=TaskPriority.CRITICAL,
        )
        
        logger.info("seed_task_published", url=url)
        
    logger.info("seeding_complete", count=len(settings.transfermarkt.seeds))


def run_worker_process(worker_type: str, worker_id: int):
    """Run a worker process."""
    # Re-configure logging in child process
    configure_logging()
    
    logger.info("worker_process_starting", type=worker_type, id=worker_id)
    
    try:
        if worker_type == "discovery":
            from scraper.workers.discovery_worker import run_discovery_worker
            asyncio.run(run_discovery_worker(worker_id))
        elif worker_type == "extraction":
            from scraper.workers.extraction_worker import run_extraction_worker
            asyncio.run(run_extraction_worker(worker_id))
        elif worker_type == "repair":
            from scraper.workers.repair_worker import run_repair_worker
            asyncio.run(run_repair_worker(worker_id))
        else:
            logger.error("unknown_worker_type", type=worker_type)
            
    except KeyboardInterrupt:
        logger.info("worker_process_interrupted", type=worker_type, id=worker_id)
    except Exception as e:
        logger.error(
            "worker_process_error",
            type=worker_type,
            id=worker_id,
            error=str(e),
            exc_info=True,
        )
    finally:
        logger.info("worker_process_stopped", type=worker_type, id=worker_id)


class WorkerManager:
    """Manages worker processes."""
    
    def __init__(
        self,
        discovery_workers: int,
        extraction_workers: int,
        repair_workers: int,
    ):
        self.discovery_workers = discovery_workers
        self.extraction_workers = extraction_workers
        self.repair_workers = repair_workers
        self.processes: list[multiprocessing.Process] = []
        
    def spawn_workers(self):
        """Spawn all worker processes."""
        logger.info(
            "spawning_workers",
            discovery=self.discovery_workers,
            extraction=self.extraction_workers,
            repair=self.repair_workers,
        )
        
        # Discovery workers
        for i in range(self.discovery_workers):
            p = multiprocessing.Process(
                target=run_worker_process,
                args=("discovery", i),
                name=f"discovery_worker_{i}",
            )
            p.start()
            self.processes.append(p)
            
        # Extraction workers
        for i in range(self.extraction_workers):
            p = multiprocessing.Process(
                target=run_worker_process,
                args=("extraction", i),
                name=f"extraction_worker_{i}",
            )
            p.start()
            self.processes.append(p)
            
        # Repair workers
        for i in range(self.repair_workers):
            p = multiprocessing.Process(
                target=run_worker_process,
                args=("repair", i),
                name=f"repair_worker_{i}",
            )
            p.start()
            self.processes.append(p)
            
        logger.info("all_workers_spawned", total=len(self.processes))
        
    def wait_for_workers(self):
        """Wait for all workers to complete."""
        logger.info("waiting_for_workers")
        
        try:
            for p in self.processes:
                p.join()
        except KeyboardInterrupt:
            logger.info("received_interrupt_signal")
            self.shutdown()
            
    def shutdown(self):
        """Gracefully shutdown all workers."""
        logger.info("shutting_down_workers")
        
        for p in self.processes:
            if p.is_alive():
                logger.info("terminating_worker", name=p.name)
                p.terminate()
                
        # Give processes time to cleanup
        for p in self.processes:
            p.join(timeout=5)
            
        # Force kill if still alive
        for p in self.processes:
            if p.is_alive():
                logger.warning("force_killing_worker", name=p.name)
                p.kill()
                
        logger.info("all_workers_stopped")


async def async_main(args):
    """Async main function."""
    # Seed initial tasks
    await seed_initial_tasks()
    
    # Start worker manager in background
    manager = WorkerManager(
        discovery_workers=args.discovery_workers,
        extraction_workers=args.extraction_workers,
        repair_workers=args.repair_workers,
    )
    
    # Setup signal handlers
    def signal_handler(signum, frame):
        logger.info("received_signal", signal=signum)
        manager.shutdown()
        sys.exit(0)
        
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Spawn workers
    manager.spawn_workers()
    
    # Wait
    manager.wait_for_workers()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Agentic Transfermarkt Scraper with vLLM and RabbitMQ"
    )
    
    parser.add_argument(
        "--discovery-workers",
        type=int,
        default=settings.workers.discovery_workers,
        help="Number of discovery worker processes",
    )
    
    parser.add_argument(
        "--extraction-workers",
        type=int,
        default=settings.workers.extraction_workers,
        help="Number of extraction worker processes",
    )
    
    parser.add_argument(
        "--repair-workers",
        type=int,
        default=settings.workers.repair_workers,
        help="Number of repair worker processes",
    )
    
    parser.add_argument(
        "--seed-only",
        action="store_true",
        help="Only seed initial tasks and exit",
    )
    
    args = parser.parse_args()
    
    # Configure logging
    configure_logging()
    
    logger.info(
        "scraper_starting",
        discovery_workers=args.discovery_workers,
        extraction_workers=args.extraction_workers,
        repair_workers=args.repair_workers,
    )
    
    if args.seed_only:
        asyncio.run(seed_initial_tasks())
        logger.info("seed_only_mode_complete")
        return
        
    # Run main async loop
    asyncio.run(async_main(args))


if __name__ == "__main__":
    # Set multiprocessing start method
    multiprocessing.set_start_method("spawn", force=True)
    main()
