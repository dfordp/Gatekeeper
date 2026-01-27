#!/usr/bin/env python3
"""
Diagnostic script to check Qdrant contents and search scores.
"""

import os
import sys
import logging

sys.path.insert(0, os.path.dirname(__file__))

from database import SessionLocal, Embedding
from qdrant_wrapper import qdrant
from embedding_service import EmbeddingService
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)


def main():
    """Check Qdrant collection and test search scores."""
    
    if qdrant is None:
        logger.error("✗ Qdrant not available")
        return
    
    db = SessionLocal()
    
    try:
        logger.info("\n" + "="*70)
        logger.info("  QDRANT DIAGNOSTIC")
        logger.info("="*70 + "\n")
        
        # Get company
        from database import Company
        company = db.query(Company).first()
        if not company:
            logger.error("No company found")
            return
        
        logger.info(f"Company: {company.name}\n")
        
        # Check collection stats
        stats = qdrant.get_company_stats(str(company.id))
        logger.info(f"Qdrant collection stats:")
        logger.info(f"  Total points: {stats['total_points']}\n")
        
        # Get embeddings from DB
        embeddings = db.query(Embedding).filter(
            Embedding.company_id == company.id,
            Embedding.is_active == True
        ).all()
        
        logger.info(f"Embeddings in PostgreSQL: {len(embeddings)}")
        for emb in embeddings:
            logger.info(f"  - {emb.source_type}: {emb.text_content[:50]}...")
        
        # Test search with similar query
        logger.info(f"\nSearching with query: 'Cannot save files in Creo'\n")
        
        query_text = "Cannot save files in Creo"
        query_vector = EmbeddingService.get_embedding_vector(query_text)
        
        if not query_vector:
            logger.error("Failed to embed query")
            return
        
        # Search WITHOUT threshold first (set to 0.0)
        logger.info("Search WITHOUT threshold (score_threshold=0.0):")
        results = qdrant.search(
            query_vector=query_vector,
            company_id=str(company.id),
            limit=5,
            score_threshold=0.0  # Get ALL results
        )
        
        if results:
            for i, result in enumerate(results, 1):
                payload = result["payload"]
                logger.info(f"  [{i}] Score: {result['score']:.4f}, Source: {payload.get('source_type')}")
                logger.info(f"       Text: {payload.get('text_content', '')[:60]}...")
        else:
            logger.info("  No results (even with threshold=0.0!)")
        # Now test with actual threshold
        actual_threshold = EmbeddingService.get_confidence_threshold("Other")
        logger.info(f"\nSearch WITH actual threshold ({actual_threshold}):")
        results_filtered = qdrant.search(
            query_vector=query_vector,
            company_id=str(company.id),
            limit=5,
            score_threshold=actual_threshold
        )
        
        if results_filtered:
            logger.info(f"  Found {len(results_filtered)} results above threshold")
            for result in results_filtered:
                logger.info(f"    Score: {result['score']:.4f}")
        else:
            logger.info(f"  No results above threshold {actual_threshold}")
            
            if results:
                logger.info(f"\n  Hint: Search returned {len(results)} results WITHOUT threshold,")
                logger.info(f"  but only {len(results_filtered)} above {actual_threshold} threshold.")
                logger.info(f"  The highest score was: {results[0]['score']:.4f}")
        
        logger.info("\n" + "="*70 + "\n")
        
    finally:
        db.close()

if __name__ == "__main__":
    main()