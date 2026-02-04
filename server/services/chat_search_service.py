# server/services/chat_search_service.py
"""
Chat Search Service - Company-filtered semantic search via Qdrant

This service provides:
1. Company-isolated vector search (filters by company_id)
2. Hybrid search combining vector similarity with text relevance
3. Solution aggregation from tickets and RCA records
4. Smart result ranking and deduplication
"""

import logging
from typing import Dict, List, Any, Optional, Tuple
from uuid import UUID
from datetime import datetime

from core.database import SessionLocal, Embedding, Ticket, RootCauseAnalysis, Company
from core.config import QDRANT_HOST, QDRANT_PORT
from utils.datetime_utils import to_iso_string
from .embedding_api_client import EmbeddingAPIClient

try:
    from qdrant_client import QdrantClient
    from qdrant_client.models import Filter, FieldCondition, MatchValue
except ImportError:
    logging.warning("Qdrant client not installed. Install with: pip install qdrant-client")
    QdrantClient = None

logger = logging.getLogger(__name__)


class ChatSearchService:
    """Service for company-filtered semantic search"""
    
    def __init__(self):
        self.qdrant_client = QdrantClient(
            host=QDRANT_HOST,
            port=QDRANT_PORT,
            timeout=30.0
        )
        self.api_client = EmbeddingAPIClient()
        self.collection_name = "tickets"
        self.top_k = 5
    
    def search_for_solutions(
        self,
        query: str,
        company_id: UUID,
        limit: int = 5,
        min_similarity: float = 0.6
    ) -> List[Dict[str, Any]]:
        """
        Search for similar solutions in company's knowledge base.
        
        Returns list of results:
        [
            {
                "ticket_id": UUID,
                "ticket_no": str,
                "similarity_score": float (0-1),
                "solution_title": str,
                "solution_description": str,
                "category": str,
                "status": str,
                "rca_available": bool,
                "source_type": str  # "resolution" | "rca" | "ticket_description"
            },
            ...
        ]
        """
        db = SessionLocal()
        try:
            # Verify company exists
            company = db.query(Company).filter(Company.id == company_id).first()
            if not company:
                logger.error(f"Company {company_id} not found")
                return []
            
            # Get query embedding
            try:
                query_vector = self.api_client.get_embedding_vector(query)
                if not query_vector:
                    logger.warning("Failed to get query embedding")
                    return []
            except Exception as e:
                logger.error(f"Embedding API error: {e}")
                return []
            
            # Query Qdrant with company filter
            # Filter: only embeddings from this company that are active
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
            
            search_result = self.qdrant_client.search(
                collection_name=self.collection_name,
                query_vector=query_vector,
                query_filter=qdrant_filter,
                limit=limit * 2,  # Get more to filter by similarity
                with_payload=True
            )
            
            results = []
            seen_tickets = set()
            
            for scored_point in search_result:
                payload = scored_point.payload
                similarity = scored_point.score
                
                # Filter by minimum similarity threshold
                if similarity < min_similarity:
                    continue
                
                ticket_id = UUID(payload.get("ticket_id"))
                
                # Avoid duplicate tickets in results
                if ticket_id in seen_tickets:
                    continue
                
                seen_tickets.add(ticket_id)
                
                # Get ticket details from database
                ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
                if not ticket:
                    continue
                
                # Get RCA if available
                rca = db.query(RootCauseAnalysis).filter(
                    RootCauseAnalysis.ticket_id == ticket_id
                ).first()
                
                result = {
                    "ticket_id": str(ticket_id),
                    "ticket_no": ticket.ticket_no,
                    "similarity_score": round(similarity, 3),
                    "solution_title": ticket.subject,
                    "solution_description": payload.get("text_content", ticket.detailed_description)[:500],
                    "category": ticket.category,
                    "status": ticket.status,
                    "rca_available": rca is not None,
                    "source_type": payload.get("source_type", "ticket_description"),
                    "created_at": to_iso_string(ticket.created_at) if ticket.created_at else None
                }
                
                # Add RCA details if available
                if rca:
                    result["rca_summary"] = rca.root_cause_description[:300]
                    result["prevention_measures"] = rca.prevention_measures
                
                results.append(result)
                
                if len(results) >= limit:
                    break
            
            logger.info(f"Found {len(results)} solutions for company {company.name}")
            return results
        
        except Exception as e:
            logger.error(f"Search error: {e}")
            return []
        
        finally:
            db.close()
    def debug_search(
        self,
        query: str,
        company_id: UUID,
        min_similarity: float = 0.0
    ) -> Dict[str, Any]:
        """
        Debug version of search that shows ALL results before filtering.
        Helps identify why exact matches aren't returning.
        """
        db = SessionLocal()
        try:
            logger.info(f"=== DEBUG SEARCH ===")
            logger.info(f"Query: {query[:100]}")
            logger.info(f"Company ID: {company_id}")
            logger.info(f"Min similarity: {min_similarity}")
            
            # Get query embedding
            query_vector = self.api_client.get_embedding_vector(query)
            if not query_vector:
                logger.error("Failed to get query embedding")
                return {"error": "No embedding"}
            
            logger.info(f"Query vector dimension: {len(query_vector)}")
            
            # Search WITHOUT filters first
            logger.info("Searching Qdrant without any filters...")
            search_all = self.qdrant_client.search(
                collection_name=self.collection_name,
                query_vector=query_vector,
                limit=20,
                with_payload=True
            )
            
            logger.info(f"Found {len(search_all)} total results in Qdrant")
            
            all_results = []
            for i, point in enumerate(search_all):
                payload = point.payload or {}
                all_results.append({
                    "rank": i + 1,
                    "score": round(point.score, 4),
                    "ticket_id": payload.get("ticket_id"),
                    "company_id": payload.get("company_id"),
                    "is_active": payload.get("is_active"),
                    "source_type": payload.get("source_type"),
                    "text_preview": payload.get("text_content", "")[:80]
                })
                
                logger.info(
                    f"Result {i+1}: score={point.score:.4f}, "
                    f"ticket_id={payload.get('ticket_id')}, "
                    f"company={payload.get('company_id')}, "
                    f"active={payload.get('is_active')}"
                )
            
            # Now search with filters
            logger.info("Searching with company_id + is_active=True filters...")
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
            
            filtered_results = self.qdrant_client.search(
                collection_name=self.collection_name,
                query_vector=query_vector,
                query_filter=qdrant_filter,
                limit=20,
                with_payload=True
            )
            
            logger.info(f"Found {len(filtered_results)} results after filtering")
            
            return {
                "query": query,
                "company_id": str(company_id),
                "all_results": all_results,
                "filtered_count": len(filtered_results),
                "filtered_results": [
                    {
                        "score": round(p.score, 4),
                        "ticket_id": p.payload.get("ticket_id"),
                        "text_preview": p.payload.get("text_content", "")[:80]
                    }
                    for p in filtered_results
                ]
            }
        
        except Exception as e:
            logger.error(f"Debug search error: {e}", exc_info=True)
            return {"error": str(e)}
        
        finally:
            db.close()
    def get_similar_tickets(
        self,
        ticket_id: UUID,
        company_id: UUID,
        limit: int = 3
    ) -> List[Dict[str, Any]]:
        """Get similar tickets to a given ticket (same company only)"""
        db = SessionLocal()
        try:
            # Get the source ticket
            source_ticket = db.query(Ticket).filter(
                Ticket.id == ticket_id,
                Ticket.company_id == company_id
            ).first()
            
            if not source_ticket:
                return []
            
            # Search using ticket subject + description
            search_text = f"{source_ticket.subject} {source_ticket.detailed_description}"
            return self.search_for_solutions(
                query=search_text,
                company_id=company_id,
                limit=limit,
                min_similarity=0.5
            )
        
        except Exception as e:
            logger.error(f"Error finding similar tickets: {e}")
            return []
        
        finally:
            db.close()