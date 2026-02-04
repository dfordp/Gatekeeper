# server/services/event_queue.py

"""
Event Queue Service for Gatekeeper Support Platform

Uses PostgreSQL LISTEN/NOTIFY for event-driven architecture.
Enables asynchronous processing of embeddings and attachments.

Architecture:
    1. Services emit events (TicketEvent, AttachmentEvent)
    2. Event emitter broadcasts via PostgreSQL NOTIFY
    3. Event listeners subscribe via LISTEN
    4. Async handlers process embeddings, searches, etc.

Responsibilities:
1. Emit events from ticket/attachment operations
2. Subscribe to events and trigger handlers
3. Manage event listeners (start/stop)
4. Provide event replay for recovery

Usage:
    from event_queue import EventQueue, EventType
    
    # Emit an event
    EventQueue.emit(
        EventType.TICKET_CREATED,
        ticket_id=ticket_id,
        company_id=company_id
    )
    
    # Listen to events
    EventQueue.subscribe(
        EventType.TICKET_CREATED,
        on_ticket_created
    )
    
    # Start listening (blocking)
    EventQueue.start_listening()
"""

import os
import sys
import logging
import json
import threading
from typing import Dict, Callable, Any, Optional
from datetime import datetime
from enum import Enum
import select
import psycopg2
import psycopg2.extensions
from dotenv import load_dotenv

from core.database import SessionLocal
from utils.datetime_utils import to_iso_string

load_dotenv()

# Setup logging
logger = logging.getLogger(__name__)

# Database URL
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://gatekeeper_user:gatekeeper_secure_password_123@localhost:5432/gatekeeper_db"
)


class EventType(Enum):
    """Supported event types."""
    TICKET_CREATED = "ticket_created"
    TICKET_UPDATED = "ticket_updated"
    TICKET_CLOSED = "ticket_closed"
    TICKET_REOPENED = "ticket_reopened"
    
    ATTACHMENT_ADDED = "attachment_added"
    ATTACHMENT_REPLACED = "attachment_replaced"
    ATTACHMENT_DEPRECATED = "attachment_deprecated"
    
    RESOLUTION_ADDED = "resolution_added"
    EMBEDDING_CREATED = "embedding_created"
    EMBEDDING_DEPRECATED = "embedding_deprecated"


class EventQueue:
    """Event queue using PostgreSQL LISTEN/NOTIFY."""
    
    # Mapping of event types to channel names
    _CHANNELS = {
        EventType.TICKET_CREATED: "ticket_created_channel",
        EventType.TICKET_UPDATED: "ticket_updated_channel",
        EventType.TICKET_CLOSED: "ticket_closed_channel",
        EventType.TICKET_REOPENED: "ticket_reopened_channel",
        EventType.ATTACHMENT_ADDED: "attachment_added_channel",
        EventType.ATTACHMENT_REPLACED: "attachment_replaced_channel",
        EventType.ATTACHMENT_DEPRECATED: "attachment_deprecated_channel",
        EventType.RESOLUTION_ADDED: "resolution_added_channel",
        EventType.EMBEDDING_CREATED: "embedding_created_channel",
        EventType.EMBEDDING_DEPRECATED: "embedding_deprecated_channel",
    }
    
    # Event handlers
    _handlers: Dict[EventType, list] = {event_type: [] for event_type in EventType}
    
    # Connection for listening
    _listener_conn = None
    _listener_thread = None
    _running = False
    _lock = threading.Lock()
    
    @staticmethod
    def emit(event_type: EventType, **data) -> bool:
        """
        Emit an event through PostgreSQL NOTIFY.
        
        Args:
            event_type: Type of event
            **data: Event payload
            
        Returns:
            True if successful
        """
        try:
            channel = EventQueue._CHANNELS.get(event_type)
            if not channel:
                logger.error(f"Unknown event type: {event_type}")
                return False
            
            # Add timestamp
            data["timestamp"] = to_iso_string(datetime.utcnow())
            data["event_type"] = event_type.value
            
            payload = json.dumps(data)
            
            # Connect and notify
            conn = psycopg2.connect(DATABASE_URL)
            conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
            cursor = conn.cursor()
            
            cursor.execute(f"NOTIFY {channel}, %s", (payload,))
            cursor.close()
            conn.close()
            
            logger.debug(f"✓ Emitted event {event_type.value}: {payload[:100]}...")
            return True
            
        except Exception as e:
            logger.error(f"Failed to emit event {event_type.value}: {e}")
            return False
    
    @staticmethod
    def subscribe(event_type: EventType, handler: Callable) -> bool:
        """
        Subscribe to an event type.
        Handler will be called when event is received.
        
        Args:
            event_type: Type of event to listen for
            handler: Callable that takes event data dict
            
        Returns:
            True if subscription successful
        """
        try:
            if event_type not in EventQueue._handlers:
                logger.error(f"Unknown event type: {event_type}")
                return False
            
            EventQueue._handlers[event_type].append(handler)
            logger.info(f"✓ Subscribed to {event_type.value}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to subscribe: {e}")
            return False
    
    @staticmethod
    def start_listening() -> None:
        """
        Start listening for events (blocking).
        Must be called in a separate thread for non-blocking operation.
        """
        try:
            logger.info("Starting event queue listener...")
            
            # Connect to database
            EventQueue._listener_conn = psycopg2.connect(DATABASE_URL)
            EventQueue._listener_conn.set_isolation_level(
                psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT
            )
            cursor = EventQueue._listener_conn.cursor()
            
            # Listen to all channels
            for channel in EventQueue._CHANNELS.values():
                cursor.execute(f"LISTEN {channel}")
                logger.info(f"  Listening to {channel}")
            
            cursor.close()
            EventQueue._running = True
            logger.info("✓ Event queue listener started")
            
            # Listen for notifications
            while EventQueue._running:
                if select.select([EventQueue._listener_conn], [], [], 5) == ([], [], []):
                    # Timeout - check if still running
                    continue
                else:
                    # Notification received
                    EventQueue._listener_conn.poll()
                    while EventQueue._listener_conn.notifies:
                        notify = EventQueue._listener_conn.notifies.pop(0)
                        EventQueue._handle_notification(notify)
            
            logger.info("Event queue listener stopped")
            
        except Exception as e:
            logger.error(f"Event listener error: {e}")
            EventQueue._running = False
        finally:
            if EventQueue._listener_conn:
                EventQueue._listener_conn.close()
                EventQueue._listener_conn = None
    
    @staticmethod
    def start_listening_async() -> threading.Thread:
        """
        Start listening for events in a background thread.
        
        Returns:
            Thread object (already started)
        """
        with EventQueue._lock:
            if EventQueue._listener_thread and EventQueue._listener_thread.is_alive():
                logger.warning("Listener thread already running")
                return EventQueue._listener_thread
            
            thread = threading.Thread(
                target=EventQueue.start_listening,
                daemon=True,
                name="EventQueueListener"
            )
            thread.start()
            EventQueue._listener_thread = thread
            return thread
    
    @staticmethod
    def stop_listening() -> None:
        """Stop the event listener."""
        with EventQueue._lock:
            EventQueue._running = False
            logger.info("Event queue listener stopping...")
    
    @staticmethod
    def _handle_notification(notify) -> None:
        """
        Handle a PostgreSQL notification.
        
        Args:
            notify: psycopg2 Notify object with channel and payload
        """
        try:
            payload = json.loads(notify.payload)
            event_type_str = payload.get("event_type")
            
            # Find matching event type
            event_type = None
            for et in EventType:
                if et.value == event_type_str:
                    event_type = et
                    break
            
            if not event_type:
                logger.warning(f"Unknown event type: {event_type_str}")
                return
            
            logger.info(f"Received event: {event_type_str}")
            
            # Call handlers
            handlers = EventQueue._handlers.get(event_type, [])
            for handler in handlers:
                try:
                    handler(payload)
                except Exception as e:
                    logger.error(f"Handler error for {event_type_str}: {e}")
        
        except Exception as e:
            logger.error(f"Failed to handle notification: {e}")