#!/usr/bin/env python3
"""
Adaptive Threshold Service

Dynamically calculates confidence thresholds based on:
1. Historical match accuracy (precision/recall)
2. Category-specific performance
3. False positive/negative rates
4. User feedback on results

Instead of hardcoded thresholds, learns what works for your data.
"""

import os
import sys
import logging
from typing import Dict, Optional
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(__file__))

from database import SessionLocal, Ticket, TicketEvent, Embedding
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class AdaptiveThresholdService:
    """Dynamically calculates confidence thresholds based on actual performance."""
    
    @staticmethod
    def calculate_optimal_thresholds(company_id: str, days: int = 30) -> Dict[str, float]:
        """
        Calculate optimal confidence thresholds based on actual search results.
        
        Analyzes:
        - How many searches found correct matches vs false positives
        - Category-specific match quality
        - User acceptance rate (feedback)
        - Precision/recall tradeoffs
        
        Args:
            company_id: UUID of company
            days: Look back at last N days of data
            
        Returns:
            Dict with optimal thresholds per category
        """
        logger.info(f"Calculating optimal thresholds for company {company_id}...")
        
        db = SessionLocal()
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=days)
            
            # Get all tickets and their categories from the past N days
            tickets = db.query(Ticket).filter(
                Ticket.company_id == company_id,
                Ticket.created_at >= cutoff_date
            ).all()
            
            if not tickets:
                logger.warning(f"No tickets found in past {days} days, using defaults")
                return AdaptiveThresholdService._get_default_thresholds()
            
            # Group tickets by category
            by_category = {}
            for ticket in tickets:
                cat = ticket.category or "Other"
                if cat not in by_category:
                    by_category[cat] = []
                by_category[cat].append(ticket)
            
            # Calculate threshold for each category
            thresholds = {}
            
            for category, cat_tickets in by_category.items():
                # Get search feedback events for these tickets
                feedback = AdaptiveThresholdService._get_search_feedback(
                    db, cat_tickets
                )
                
                if feedback:
                    # Calculate optimal threshold from feedback
                    threshold = AdaptiveThresholdService._calculate_category_threshold(
                        feedback
                    )
                    thresholds[category] = threshold
                else:
                    # No feedback, use default
                    thresholds[category] = 0.55
                
                logger.info(f"  Category '{category}': {len(cat_tickets)} tickets, threshold={thresholds[category]:.2f}")
            
            logger.info(f"✓ Calculated thresholds for {len(thresholds)} categories")
            return thresholds
            
        except Exception as e:
            logger.error(f"Failed to calculate thresholds: {e}")
            return AdaptiveThresholdService._get_default_thresholds()
        finally:
            db.close()
    
    @staticmethod
    def _get_search_feedback(db, tickets: list) -> list:
        """
        Get search feedback events (user ratings) for tickets.
        
        Looks for events like:
        - "search_result_helpful" (user found the result good)
        - "search_result_not_helpful" (false positive/negative)
        - "search_result_rating" (0-5 rating)
        """
        feedback = []
        
        for ticket in tickets:
            events = db.query(TicketEvent).filter(
                TicketEvent.ticket_id == ticket.id,
                TicketEvent.event_type.in_([
                    'search_result_helpful',
                    'search_result_not_helpful',
                    'search_result_rating'
                ])
            ).all()
            
            for event in events:
                feedback.append({
                    'ticket_id': ticket.id,
                    'category': ticket.category,
                    'event_type': event.event_type,
                    'payload': event.payload,
                    'timestamp': event.created_at
                })
        
        return feedback
    
    @staticmethod
    def _calculate_category_threshold(feedback: list) -> float:
        """
        Calculate optimal threshold for a category based on feedback.
        
        Logic:
        - If many false positives → increase threshold (be more selective)
        - If many false negatives → decrease threshold (be more inclusive)
        - Aim for ~80% precision + ~70% recall balance
        
        Args:
            feedback: List of feedback events
            
        Returns:
            Optimal threshold (0.0-1.0)
        """
        if not feedback:
            return 0.55
        
        helpful = sum(1 for f in feedback if f['event_type'] == 'search_result_helpful')
        not_helpful = sum(1 for f in feedback if f['event_type'] == 'search_result_not_helpful')
        
        total = helpful + not_helpful
        if total == 0:
            return 0.55
        
        # Calculate precision
        precision = helpful / total if total > 0 else 0
        
        # Adjust threshold based on precision
        # High precision (good) → threshold is good
        # Low precision (false positives) → increase threshold
        if precision >= 0.80:
            return 0.50  # Can be more inclusive
        elif precision >= 0.70:
            return 0.55
        elif precision >= 0.60:
            return 0.60
        else:
            return 0.65  # Be more selective
    
    @staticmethod
    def _get_default_thresholds() -> Dict[str, float]:
        """Get sensible default thresholds."""
        return {
            "Login / Access": 0.55,
            "License": 0.55,
            "Performance": 0.50,
            "Installation": 0.55,
            "Upload or Save": 0.55,
            "Workflow": 0.50,
            "Integration": 0.55,
            "Data / Configuration": 0.55,
            "Other": 0.55
        }
    
    @staticmethod
    def record_search_feedback(
        ticket_id: str,
        search_confidence: float,
        was_helpful: bool,
        rating: Optional[int] = None
    ) -> bool:
        """
        Record user feedback about a search result.
        
        This trains the system to learn what thresholds work best.
        
        Args:
            ticket_id: UUID of the ticket from search result
            search_confidence: The confidence score that was returned
            was_helpful: True if user found it helpful
            rating: Optional 0-5 rating
            
        Returns:
            True if recorded successfully
        """
        logger.info(f"Recording search feedback: helpful={was_helpful}, confidence={search_confidence:.2f}")
        
        db = SessionLocal()
        try:
            ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
            if not ticket:
                return False
            
            # Create feedback event
            event = TicketEvent(
                ticket_id=ticket_id,
                event_type="search_result_helpful" if was_helpful else "search_result_not_helpful",
                actor_user_id=ticket.raised_by_user_id,  # Or could be from a feedback API
                payload={
                    "confidence": search_confidence,
                    "rating": rating,
                    "timestamp": datetime.utcnow().isoformat()
                }
            )
            db.add(event)
            db.commit()
            
            return True
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to record feedback: {e}")
            return False
        finally:
            db.close()