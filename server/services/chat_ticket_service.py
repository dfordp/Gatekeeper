# server/services/chat_ticket_service.py
"""
Chat Ticket Service - Adaptive ticket creation with category inference

This service:
1. Uses ChatGroqService to extract intent and category from user message
2. Gets adaptive thresholds based on vector DB performance
3. Searches for similar solutions with category-specific confidence thresholds
4. Infers category from top search result if above adaptive threshold
5. Calls existing TicketCreationService with smart category mapping
6. Leverages existing event emission and task queue
7. Extracts vision context from images to enrich analysis
"""

import logging
import base64
from typing import Dict, Any, Optional
from uuid import UUID
from datetime import date, datetime

from core.database import SessionLocal, User, Company, Ticket, ChatSession
from utils.datetime_utils import to_iso_date
from .ticket_creation_service import TicketCreationService
from .chat_search_service import ChatSearchService
from utils.exceptions import ValidationError, NotFoundError


logger = logging.getLogger(__name__)


class ChatTicketService:
    """Service for creating tickets from chat context with adaptive category mapping"""
    
    # Cache for adaptive thresholds (refresh periodically)
    _threshold_cache = {}
    _threshold_cache_time = {}
    THRESHOLD_CACHE_TTL = 3600  # 1 hour
    
    def __init__(self):
        self.search_service = ChatSearchService()
        self.groq_service = None  # Lazy initialization
    
    def _get_groq_service(self):
        """Lazy initialize Groq service, handle missing API key gracefully"""
        if self.groq_service is None:
            try:
                from .chat_groq_service import ChatGroqService
                self.groq_service = ChatGroqService()
                logger.info("✓ ChatGroqService initialized")
            except ValueError as e:
                logger.warning(f"ChatGroqService unavailable: {e} - will skip intent extraction")
                self.groq_service = False  # Mark as attempted but failed
            except Exception as e:
                logger.warning(f"Failed to initialize ChatGroqService: {e}")
                self.groq_service = False
        
        return self.groq_service if self.groq_service else None
    
    def analyze_issue_for_chat(
        self,
        chat_session_id: UUID,
        issue_description: str,
        image_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Analyze an issue WITHOUT creating a ticket.
        
        This is used in the chat flow to:
        1. Extract vision context from image if provided
        2. Extract category via Groq with enriched description
        3. Get adaptive threshold
        4. Search for similar solutions
        5. Return analysis for user confirmation
        
        Args:
            chat_session_id: ID of the chat session
            issue_description: Text description of the issue
            image_path: Optional path to image for vision analysis
        
        Returns:
        {
            "inferred_category": str,
            "adaptive_threshold": float,
            "similar_solutions": [
                {
                    "ticket_no": str,
                    "similarity_score": float,
                    "subject": str,
                    "solution_description": str,
                    "category": str
                },
                ...
            ],
            "groq_intent": str,
            "groq_confidence": float,
            "vision_context": str (optional)
        }
        """
        db = SessionLocal()
        try:
            # Get chat session
            chat_session = db.query(ChatSession).filter(
                ChatSession.id == chat_session_id
            ).first()
            
            if not chat_session:
                raise NotFoundError("Chat session not found")
            
            company = db.query(Company).filter(Company.id == chat_session.company_id).first()
            if not company:
                raise NotFoundError("Company not found")
            
            # Validate issue description
            if not issue_description or len(issue_description.strip()) < 10:
                raise ValidationError("Issue description must be at least 10 characters")
            
            # Step 0: Extract vision context from image if provided
            vision_context = None
            enriched_description = issue_description
            
            if image_path:
                try:
                    vision_context = self._extract_vision_context(image_path)
                    if vision_context:
                        logger.info(f"Vision analysis: {vision_context[:100]}...")
                        # Enhance description with vision context for better analysis
                        enriched_description = f"{issue_description}\n\nVisual Context: {vision_context}"
                except Exception as e:
                    logger.warning(f"Failed to analyze image: {e}")
            
            # Step 1: Extract intent + category via Groq
            groq_category = None
            groq_confidence = 0
            groq_intent = None
            
            groq_service = self._get_groq_service()
            if groq_service:
                try:
                    logger.info(f"Analyzing issue for company {company.name}")
                    intent_result = groq_service.extract_intent_and_data(
                        user_message=enriched_description,
                        company_id=chat_session.company_id,
                        user_id=chat_session.user_id
                    )
                    
                    groq_category = intent_result.get("entities", {}).get("category")
                    groq_confidence = intent_result.get("confidence", 50)
                    groq_intent = intent_result.get("intent")
                    
                    logger.info(
                        f"Groq analysis: intent={groq_intent}, "
                        f"category={groq_category}, confidence={groq_confidence}"
                    )
                
                except Exception as e:
                    logger.warning(f"Failed to extract intent via Groq: {e}")
            
            # Step 2: Get adaptive threshold
            # If image was provided, lower threshold slightly for better context matching
            adaptive_threshold = self._get_adaptive_threshold(
                company_id=chat_session.company_id,
                category=groq_category,
                has_image=bool(image_path)
            )
            
            logger.info(f"Adaptive threshold: {adaptive_threshold:.3f} for category '{groq_category}'")
            
            # Step 3: Search for similar solutions
            similar_solutions = []
            inferred_category = groq_category
            
            try:
                search_results = self.search_service.search_for_solutions(
                    query=enriched_description,
                    company_id=chat_session.company_id,
                    limit=3,
                    min_similarity=adaptive_threshold
                )
                
                if search_results:
                    # Use the category from the top result
                    top_result = search_results[0]
                    inferred_category = top_result.get("category") or groq_category
                    
                    # Format results for display
                    similar_solutions = [
                        {
                            "ticket_no": r.get("ticket_no"),
                            "similarity_score": r.get("similarity_score"),
                            "subject": r.get("solution_title"),
                            "solution_description": r.get("solution_description"),
                            "category": r.get("category"),
                            "status": r.get("status")
                        }
                        for r in search_results
                    ]
                    
                    logger.info(f"Found {len(similar_solutions)} similar solutions")
            
            except Exception as e:
                logger.warning(f"Failed to search for solutions: {e}")
            
            # Validate category
            valid_categories = [
                "login-access", "license", "installation", "upload-save",
                "workflow", "performance", "integration", "data-configuration", "other"
            ]
            if inferred_category and inferred_category not in valid_categories:
                inferred_category = groq_category or "other"
            
            result = {
                "inferred_category": inferred_category or "other",
                "adaptive_threshold": round(adaptive_threshold, 3),
                "similar_solutions": similar_solutions,
                "groq_intent": groq_intent,
                "groq_confidence": groq_confidence
            }
            
            # Include vision context in result if available
            if vision_context:
                result["vision_context"] = vision_context
            
            return result
        
        finally:
            db.close()
    
    def _extract_vision_context(self, image_path: str) -> Optional[str]:
        """
        Extract vision context from image using Groq Vision API.
        
        Describes what's in the image to provide context for issue analysis.
        This helps with categorization and finding similar solutions.
        
        Args:
            image_path: Path to the image file
        
        Returns:
            Description of image content, or None if extraction fails
        """
        try:
            import os
            
            if not os.path.exists(image_path):
                logger.warning(f"Image path not found: {image_path}")
                return None
            
            # Use Groq's vision analysis (already initialized in _get_groq_service)
            groq_service = self._get_groq_service()
            if not groq_service:
                logger.warning("ChatGroqService unavailable for vision analysis")
                return None
            
            # Analyze image using Groq Vision
            vision_result = groq_service.analyze_image(
                image_path=image_path,
                context="Issue troubleshooting screenshot"
            )
            
            # Extract description from analysis result
            vision_text = vision_result.get("description", "").strip()
            
            if vision_text:
                # Take first 300 chars to keep enriched description reasonable
                vision_context = vision_text[:300]
                logger.info(f"✓ Vision analysis complete: {len(vision_context)} chars")
                return vision_context
            
            return None
        
        except Exception as e:
            logger.warning(f"Vision analysis failed: {e}")
            return None
    
    
    def create_ticket_from_chat(
            self,
            chat_session_id: UUID,
            issue_description: str,
            inferred_category: str,
        ) -> Optional[Dict[str, Any]]:
            """
            Create ticket from chat session.
            Ticket number is generated atomically by create_ticket() - do NOT pre-generate it.
            """
            db = SessionLocal()
            try:
                chat_session = db.query(ChatSession).filter(
                    ChatSession.id == chat_session_id
                ).first()
    
                if not chat_session:
                    raise ValidationError("Chat session not found")
    
                logger.info(f"Creating ticket from chat session {chat_session_id}")
    
                # Pass ticket_no=None to let create_ticket() generate it atomically
                # This prevents race conditions with other concurrent ticket creations
                ticket_result = TicketCreationService.create_ticket(
                    subject=issue_description[:100],
                    detailed_description=issue_description,
                    company_id=str(chat_session.company_id),
                    raised_by_user_id=str(chat_session.user_id),
                    category=inferred_category,
                    level="level-1",
                    created_at=date.today(),
                    created_by_admin_id=None,
                    ticket_no=None  # CRITICAL: Let create_ticket generate this atomically
                )
    
                logger.info(f"✓ Ticket created: {ticket_result.get('ticket_no')}")
                return ticket_result
    
            except Exception as e:
                logger.error(f"Error creating ticket from chat: {e}", exc_info=True)
                raise
    
            finally:
                db.close()
        
    def _get_adaptive_threshold(
        self,
        company_id: UUID,
        category: Optional[str] = None,
        has_image: bool = False
    ) -> float:
        """
        Get adaptive threshold for a category.
        
        Calculates thresholds based on historical feedback in vector DB:
        - How well that category performs in search (precision)
        - False positive/negative rates
        - User feedback on results
        
        If has_image is True, slightly lowers the threshold since images
        provide additional context for better matching.
        
        Returns threshold value (0.0-1.0) that adapts based on actual performance.
        """
        
        company_id_str = str(company_id)
        now = datetime.utcnow().timestamp()
        
        # Check if we have cached thresholds for this company
        if company_id_str in self._threshold_cache:
            cache_time = self._threshold_cache_time.get(company_id_str, 0)
            if now - cache_time < self.THRESHOLD_CACHE_TTL:
                thresholds = self._threshold_cache[company_id_str]
                category_key = category or "other"
                threshold = thresholds.get(category_key.lower(), 0.55)
                
                # Lower threshold if image was provided (more context = better matching)
                if has_image:
                    threshold = max(0.45, threshold - 0.05)
                
                return threshold
        
        # Calculate adaptive thresholds from actual search feedback
        try:
            thresholds = self._calculate_thresholds_from_feedback(company_id)
            
            # Cache the thresholds
            self._threshold_cache[company_id_str] = thresholds
            self._threshold_cache_time[company_id_str] = now
            
            logger.info(f"Calculated adaptive thresholds for company {company_id_str}: {thresholds}")
            
            category_key = category or "other"
            threshold = thresholds.get(category_key.lower(), 0.55)
            
            # Lower threshold if image was provided
            if has_image:
                threshold = max(0.45, threshold - 0.05)
            
            return threshold
        
        except Exception as e:
            logger.warning(f"Failed to calculate adaptive thresholds: {e}, using defaults")
        
        # Fallback to sensible defaults
        threshold = self._get_default_threshold(category)
        if has_image:
            threshold = max(0.45, threshold - 0.05)
        
        return threshold
    
    @staticmethod
    def _calculate_thresholds_from_feedback(company_id: UUID) -> Dict[str, float]:
        """
        Calculate adaptive thresholds by analyzing Qdrant search results per category.
        
        Strategy: For each category, sample existing tickets and measure what similarity
        scores typically return results in that category. Use this to set optimal thresholds.
        
        - If solutions found at 0.50 score in category X → can use 0.50 threshold
        - If no results until 0.60 in category Y → needs 0.60 threshold
        """
        db = SessionLocal()
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.models import Filter, FieldCondition, MatchValue
            from .embedding_api_client import EmbeddingAPIClient
            from datetime import timedelta
            
            # Initialize Qdrant and embedding client
            qdrant_client = QdrantClient(
                host="qdrant",  # Docker service name
                port=6333,
                timeout=30.0
            )
            embedding_client = EmbeddingAPIClient()
            
            # Get all tickets in company by category
            company_tickets = db.query(Ticket).filter(
                Ticket.company_id == company_id
            ).all()
            
            if not company_tickets:
                return ChatTicketService._get_default_thresholds()
            
            # Group tickets by category
            by_category = {}
            for ticket in company_tickets:
                cat = (ticket.category or "other").lower()
                if cat not in by_category:
                    by_category[cat] = []
                by_category[cat].append(ticket)
            
            thresholds = {}
            
            # For each category, analyze what similarity scores typically match
            for cat, tickets in by_category.items():
                if not tickets:
                    thresholds[cat] = 0.55
                    continue
                
                # Take sample tickets (up to 3) and check their search results
                sample_tickets = tickets[:3]
                similarity_scores = []
                
                for sample_ticket in sample_tickets:
                    try:
                        # Get embedding of this ticket
                        search_text = f"{sample_ticket.subject} {sample_ticket.detailed_description}"
                        query_vector = embedding_client.get_embedding_vector(search_text)
                        
                        if not query_vector:
                            continue
                        
                        # Search in Qdrant for this category
                        qdrant_filter = Filter(
                            must=[
                                FieldCondition(
                                    key="company_id",
                                    match=MatchValue(value=str(company_id))
                                ),
                                FieldCondition(
                                    key="is_active",
                                    match=MatchValue(value=True)
                                )
                            ]
                        )
                        
                        search_result = qdrant_client.search(
                            collection_name="tickets",
                            query_vector=query_vector,
                            query_filter=qdrant_filter,
                            limit=10,
                            with_payload=True
                        )
                        
                        # Collect similarity scores of results in same category
                        for scored_point in search_result:
                            payload = scored_point.payload
                            ticket_id = payload.get("ticket_id")
                            
                            # Skip self
                            if ticket_id == str(sample_ticket.id):
                                continue
                            
                            result_ticket = db.query(Ticket).filter(
                                Ticket.id == UUID(ticket_id)
                            ).first()
                            
                            # If result is in same category, record its score
                            if result_ticket and (result_ticket.category or "other").lower() == cat:
                                similarity_scores.append(scored_point.score)
                    
                    except Exception as e:
                        logger.debug(f"Error sampling category {cat}: {e}")
                        continue
                
                # Calculate optimal threshold based on collected scores
                if similarity_scores:
                    # Use 25th percentile (lower quartile) of matching scores
                    # This ensures 75% of category matches are found
                    similarity_scores.sort()
                    percentile_25_idx = max(0, len(similarity_scores) // 4)
                    optimal_score = similarity_scores[percentile_25_idx]
                    
                    # Set threshold slightly below optimal to catch more matches
                    threshold = max(0.45, optimal_score - 0.05)
                    
                    logger.info(
                        f"Category '{cat}': {len(tickets)} tickets, {len(similarity_scores)} matches sampled, "
                        f"25th percentile={optimal_score:.3f}, threshold={threshold:.3f}"
                    )
                else:
                    # No same-category matches found in Qdrant
                    # This is normal for new/sparse categories - use adaptive default
                    # If category has only 1 ticket: higher threshold (need more precision)
                    # If category has multiple tickets: lower threshold (can afford to be inclusive)
                    if len(tickets) >= 3:
                        threshold = 0.50  # More data = can be inclusive
                    elif len(tickets) >= 2:
                        threshold = 0.55  # Moderate
                    else:
                        threshold = 0.60  # Single ticket = be selective
                    
                    logger.info(
                        f"Category '{cat}': {len(tickets)} tickets, no same-category matches in Qdrant, "
                        f"using adaptive threshold {threshold:.2f}"
                    )
                
                thresholds[cat] = threshold
            
            # Fill in missing categories with defaults
            for cat in ChatTicketService._get_default_thresholds().keys():
                if cat not in thresholds:
                    thresholds[cat] = 0.55
            
            return thresholds if thresholds else ChatTicketService._get_default_thresholds()
        
        except Exception as e:
            logger.warning(f"Error calculating thresholds from Qdrant: {e}")
            logger.info("Falling back to default thresholds")
            return ChatTicketService._get_default_thresholds()
        
        finally:
            db.close()
    
    @staticmethod
    def _get_default_threshold(category: Optional[str] = None) -> float:
        """Get default threshold for a category"""
        defaults = ChatTicketService._get_default_thresholds()
        category_key = (category or "other").lower()
        return defaults.get(category_key, 0.55)
    
    @staticmethod
    def _get_default_thresholds() -> Dict[str, float]:
        """Get all default thresholds"""
        return {
            "login-access": 0.55,
            "license": 0.55,
            "performance": 0.50,
            "installation": 0.55,
            "upload-save": 0.55,
            "workflow": 0.50,
            "integration": 0.55,
            "data-configuration": 0.55,
            "other": 0.55
        }
    
    @staticmethod
    def get_ticket_status(ticket_id: UUID) -> Dict[str, Any]:
        """Get current status of a ticket"""
        db = SessionLocal()
        try:
            ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
            if not ticket:
                raise NotFoundError("Ticket not found")
            
            return {
                "ticket_id": str(ticket.id),
                "ticket_no": ticket.ticket_no,
                "status": ticket.status,
                "subject": ticket.subject,
                "category": ticket.category,
                "updated_at": to_iso_date(ticket.updated_at)
            }
        
        finally:
            db.close()