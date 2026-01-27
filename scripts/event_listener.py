#!/usr/bin/env python3
"""
Event Listener Daemon

Starts listening for events and processes them asynchronously.
This runs as a background service that responds to ticket/attachment events.

Usage:
    python scripts/event_listener.py
    
    # Stop with Ctrl+C
"""

import os
import sys
import logging
import signal

# Add parent directory to path
sys.path.insert(0, os.path.dirname(__file__))

from event_queue import EventQueue, EventType, EventHandlers
from dotenv import load_dotenv

load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def setup_handlers():
    """Register all event handlers."""
    logger.info("Setting up event handlers...")
    
    # Ticket events
    EventQueue.subscribe(EventType.TICKET_CREATED, EventHandlers.on_ticket_created)
    EventQueue.subscribe(EventType.TICKET_CLOSED, EventHandlers.on_ticket_closed)
    
    # Attachment events
    EventQueue.subscribe(EventType.ATTACHMENT_ADDED, EventHandlers.on_attachment_added)
    
    # Resolution events
    EventQueue.subscribe(EventType.RESOLUTION_ADDED, EventHandlers.on_resolution_added)
    
    # Embedding events
    EventQueue.subscribe(EventType.EMBEDDING_DEPRECATED, EventHandlers.on_embedding_deprecated)
    
    logger.info("✓ Event handlers registered\n")


def signal_handler(sig, frame):
    """Handle shutdown signals."""
    logger.info("\nShutting down event listener...")
    EventQueue.stop_listening()
    sys.exit(0)


def main():
    """Start the event listener daemon."""
    
    logger.info("\n" + "="*70)
    logger.info("  EVENT LISTENER DAEMON")
    logger.info("="*70 + "\n")
    
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Setup handlers
    setup_handlers()
    
    # Start listening
    logger.info("Starting event listener (press Ctrl+C to stop)...\n")
    
    try:
        EventQueue.start_listening()
    except KeyboardInterrupt:
        logger.info("\nReceived interrupt signal")
    except Exception as e:
        logger.error(f"Event listener error: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())