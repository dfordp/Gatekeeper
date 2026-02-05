# server/services/ticket_request_queue.py
"""
Ticket Request Queue System

Manages async task queuing for ticket operations with retry logic and failure tracking.
Provides status tracking and polling capabilities.

Task types:
- attachment_processing: Upload and process attachments
- embedding_creation: Create embeddings for ticket content
- rca_creation: Create RCA with embeddings
- qdrant_sync: Sync embeddings to Qdrant (via event)
"""

import logging
import time
from typing import Optional, Dict, Any, List
from datetime import datetime
from enum import Enum
from uuid import UUID, uuid4

from utils.datetime_utils import to_iso_date
from sqlalchemy.orm import Session
from core.database import SessionLocal
from core.logger import get_logger

logger = get_logger(__name__)


class TaskType(str, Enum):
    """Supported task types"""
    TICKET_CREATION = "ticket_creation"
    ATTACHMENT_PROCESSING = "attachment_processing"
    EMBEDDING_CREATION = "embedding_creation"
    RCA_CREATION = "rca_creation"
    QDRANT_SYNC = "qdrant_sync"


class TaskStatus(str, Enum):
    """Task execution status"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    RETRYING = "retrying"


class QueuedTaskModel:
    """In-memory representation of a queued task"""
    
    def __init__(
        self,
        task_id: str,
        ticket_id: str,
        task_type: TaskType,
        payload: Dict[str, Any],
        max_retries: int = 3
    ):
        self.task_id = task_id
        self.ticket_id = ticket_id
        self.task_type = task_type
        self.payload = payload
        self.status = TaskStatus.PENDING
        self.retry_count = 0
        self.max_retries = max_retries
        self.error_message: Optional[str] = None
        self.created_at = datetime.utcnow()
        self.started_at: Optional[datetime] = None
        self.completed_at: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation"""
        return {
            "task_id": self.task_id,
            "ticket_id": self.ticket_id,
            "task_type": self.task_type.value,
            "status": self.status.value,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "error_message": self.error_message,
            "created_at": to_iso_date(self.created_at),
            "started_at": to_iso_date(self.started_at) if self.started_at else None,
            "completed_at": to_iso_date(self.completed_at) if self.completed_at else None
        }


class TicketRequestQueue:
    """Manager for queued ticket operations"""
    
    # In-memory task store (key: task_id)
    _tasks: Dict[str, QueuedTaskModel] = {}
    _ticket_tasks: Dict[str, List[str]] = {}  # Ticket ID → List of task IDs
    
    # Configuration
    RETRY_DELAYS = [1, 2, 4]  # Exponential backoff in seconds
    MAX_QUEUE_SIZE = 1000
    
    @staticmethod
    def queue_task(
        ticket_id: str,
        task_type: TaskType,
        payload: Dict[str, Any],
        max_retries: int = 3
    ) -> str:
        """
        Queue a new task
        
        Args:
            ticket_id: UUID of the ticket
            task_type: Type of task
            payload: Task-specific data
            max_retries: Max number of retries
            
        Returns:
            task_id
        """
        if len(TicketRequestQueue._tasks) >= TicketRequestQueue.MAX_QUEUE_SIZE:
            logger.error("Queue is full")
            raise Exception("Queue is full")
        
        task_id = str(uuid4())
        task = QueuedTaskModel(task_id, ticket_id, task_type, payload, max_retries)
        
        TicketRequestQueue._tasks[task_id] = task
        
        # Track task by ticket
        if ticket_id not in TicketRequestQueue._ticket_tasks:
            TicketRequestQueue._ticket_tasks[ticket_id] = []
        TicketRequestQueue._ticket_tasks[ticket_id].append(task_id)
        
        logger.info(f"✓ Task queued: {task_type.value} for ticket {ticket_id} (task_id={task_id})")
        return task_id
    
    @staticmethod
    def get_task_status(task_id: str) -> Optional[Dict[str, Any]]:
        """Get status of a specific task"""
        task = TicketRequestQueue._tasks.get(task_id)
        if not task:
            return None
        return task.to_dict()
    
    @staticmethod
    def get_ticket_tasks(ticket_id: str) -> Dict[str, Dict[str, Any]]:
        """Get all tasks for a ticket"""
        task_ids = TicketRequestQueue._ticket_tasks.get(ticket_id, [])
        return {
            task_id: TicketRequestQueue._tasks[task_id].to_dict()
            for task_id in task_ids
            if task_id in TicketRequestQueue._tasks
        }
    
    @staticmethod
    def mark_processing(task_id: str) -> bool:
        """Mark task as processing"""
        task = TicketRequestQueue._tasks.get(task_id)
        if not task:
            return False
        
        task.status = TaskStatus.PROCESSING
        task.started_at = datetime.utcnow()
        logger.info(f"Task {task_id} marked as processing")
        return True
    
    @staticmethod
    def mark_completed(task_id: str) -> bool:
        """Mark task as completed"""
        task = TicketRequestQueue._tasks.get(task_id)
        if not task:
            return False
        
        task.status = TaskStatus.COMPLETED
        task.completed_at = datetime.utcnow()
        logger.info(f"✓ Task {task_id} completed")
        return True
    
    @staticmethod
    def mark_failed(task_id: str, error_message: str, should_retry: bool = True) -> bool:
        """
        Mark task as failed
        
        Args:
            task_id: Task ID
            error_message: Error description
            should_retry: Whether to retry if retries remain
            
        Returns:
            True if retry scheduled, False if max retries exceeded
        """
        task = TicketRequestQueue._tasks.get(task_id)
        if not task:
            return False
        
        task.error_message = error_message
        
        if should_retry and task.retry_count < task.max_retries:
            task.retry_count += 1
            task.status = TaskStatus.RETRYING
            
            delay = TicketRequestQueue.RETRY_DELAYS[task.retry_count - 1] if task.retry_count <= len(TicketRequestQueue.RETRY_DELAYS) else TicketRequestQueue.RETRY_DELAYS[-1]
            
            logger.warning(f"Task {task_id} failed (attempt {task.retry_count}/{task.max_retries}), retrying in {delay}s: {error_message}")
            
            # In a real system, this would be scheduled via Celery/RQ
            # For now, just mark for retry
            return True
        else:
            task.status = TaskStatus.FAILED
            task.completed_at = datetime.utcnow()
            logger.error(f"✗ Task {task_id} failed permanently: {error_message}")
            return False
    
    @staticmethod
    def mark_skipped(task_id: str, reason: str) -> bool:
        """Mark task as skipped"""
        task = TicketRequestQueue._tasks.get(task_id)
        if not task:
            return False
        
        task.status = TaskStatus.SKIPPED
        task.error_message = reason
        task.completed_at = datetime.utcnow()
        logger.info(f"Task {task_id} skipped: {reason}")
        return True
    
    @staticmethod
    def get_ticket_status(ticket_id: str) -> Dict[str, Any]:
        """Get comprehensive status for all tasks of a ticket"""
        tasks = TicketRequestQueue.get_ticket_tasks(ticket_id)
        
        status_breakdown = {
            "pending": 0,
            "processing": 0,
            "completed": 0,
            "failed": 0,
            "skipped": 0,
            "retrying": 0
        }
        
        for task_data in tasks.values():
            status = task_data["status"]
            if status in status_breakdown:
                status_breakdown[status] += 1
        
        overall_status = "completed"
        if status_breakdown["failed"] > 0:
            overall_status = "error"
        elif status_breakdown["processing"] > 0 or status_breakdown["retrying"] > 0:
            overall_status = "processing"
        elif status_breakdown["pending"] > 0:
            overall_status = "pending"
        
        return {
            "ticket_id": ticket_id,
            "overall_status": overall_status,
            "task_breakdown": status_breakdown,
            "tasks": tasks,
            "total_tasks": len(tasks),
            "completed_tasks": status_breakdown["completed"] + status_breakdown["skipped"],
            "failed_tasks": status_breakdown["failed"],
            "in_progress_tasks": status_breakdown["processing"] + status_breakdown["retrying"]
        }
    
    @staticmethod
    def cleanup_old_tasks(hours: int = 24) -> int:
        """Clean up completed tasks older than specified hours"""
        cutoff_time = datetime.utcnow()
        cutoff_time = cutoff_time.replace(hour=cutoff_time.hour - hours)
        
        removed = 0
        task_ids_to_remove = []
        
        for task_id, task in TicketRequestQueue._tasks.items():
            if task.completed_at and task.completed_at < cutoff_time:
                if task.status in [TaskStatus.COMPLETED, TaskStatus.SKIPPED, TaskStatus.FAILED]:
                    task_ids_to_remove.append(task_id)
        
        for task_id in task_ids_to_remove:
            del TicketRequestQueue._tasks[task_id]
            removed += 1
        
        logger.info(f"Cleaned up {removed} old tasks")
        return removed
    
    @staticmethod
    def get_stats() -> Dict[str, Any]:
        """Get queue statistics"""
        total = len(TicketRequestQueue._tasks)
        status_counts = {
            "pending": 0,
            "processing": 0,
            "completed": 0,
            "failed": 0,
            "skipped": 0,
            "retrying": 0
        }
        
        for task in TicketRequestQueue._tasks.values():
            if task.status.value in status_counts:
                status_counts[task.status.value] += 1
        
        type_counts = {}
        for task in TicketRequestQueue._tasks.values():
            task_type = task.task_type.value
            type_counts[task_type] = type_counts.get(task_type, 0) + 1
        
        return {
            "total_tasks": total,
            "status_breakdown": status_counts,
            "type_breakdown": type_counts,
            "queue_capacity_used": f"{(total / TicketRequestQueue.MAX_QUEUE_SIZE * 100):.1f}%"
        }


class QueuedTaskProcessor:
    """Utility class to process queued tasks"""
    
    @staticmethod
    def process_task(task_id: str, handler_func) -> bool:
        """
        Process a single task with error handling
        
        Args:
            task_id: Task ID to process
            handler_func: Async function to execute
            
        Returns:
            True if successful
        """
        task = TicketRequestQueue._tasks.get(task_id)
        if not task:
            logger.error(f"Task {task_id} not found")
            return False
        
        TicketRequestQueue.mark_processing(task_id)
        
        try:
            # Execute handler
            result = handler_func(task.payload)
            
            TicketRequestQueue.mark_completed(task_id)
            return True
        
        except Exception as e:
            should_retry = TicketRequestQueue.mark_failed(task_id, str(e), should_retry=True)
            if not should_retry:
                logger.error(f"Task {task_id} failed permanently after all retries")
            return False