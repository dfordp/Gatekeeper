#!/usr/bin/env python3
"""
Attachment Processor for Gatekeeper Support Platform

Responsibilities:
1. Listen to AttachmentEvent (attachment_added)
2. Extract text from PDF/image attachments
3. Chunk text into manageable pieces
4. Create Embedding records for each chunk
5. Handle attachment replacement and deprecation

Usage:
    from attachment_processor import AttachmentProcessor
    
    # Process a newly uploaded RCA document
    count = AttachmentProcessor.process_rca_attachment(
        attachment_id, ticket_id, company_id
    )
    
    # Replace an RCA with a newer version
    success = AttachmentProcessor.replace_attachment(
        old_attachment_id, new_attachment_id, ticket_id, company_id, actor_user_id
    )
    
    # Deprecate an attachment
    success = AttachmentProcessor.deprecate_attachment(
        attachment_id, actor_user_id, reason="incorrect_analysis"
    )
"""

import os
import sys
import logging
from typing import Optional, List
from datetime import datetime
import uuid

from utils.datetime_utils import to_iso_string

# Add parent directory to path
sys.path.insert(0, os.path.dirname(__file__))

from database import get_db_context, SessionLocal, Ticket, Attachment, AttachmentEvent, Embedding
from embedding_service import EmbeddingService
from dotenv import load_dotenv

load_dotenv()

# Setup logging
logger = logging.getLogger(__name__)

# Try to import PDF library
try:
    from PyPDF2 import PdfReader
    HAS_PDF = True
    logger.info("✓ PyPDF2 available for PDF processing")
except ImportError:
    HAS_PDF = False
    logger.warning("⚠ PyPDF2 not installed, PDF processing will not work")


class AttachmentProcessor:
    """Service to process attachments and create embeddings."""
    
    # Configuration
    SUPPORTED_TYPES = ['rca', 'document', 'log', 'image']
    PDF_MIME_TYPES = ['application/pdf', 'application/x-pdf']

    @staticmethod
    def _create_sample_pdf(file_path: str) -> bool:
        """
        Create a sample RCA document as plain text.
        Much simpler and easier to test than actual PDFs.
        
        Args:
            file_path: Path where the file should be created
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Create directory if it doesn't exist
            directory = os.path.dirname(file_path)
            if directory:
                os.makedirs(directory, exist_ok=True)
            
            # Always save as .txt for simplicity
            text_file_path = file_path.replace('.pdf', '.txt')
            
            content = """Root Cause Analysis: Creo Cache Issue

ISSUE SUMMARY:
Users unable to save files in Creo 11.0 after upgrade.
Error: 'Disk I/O error - cache path invalid'

ENVIRONMENT:
- Software: Creo 11.0.1.0
- OS: Windows 10 Enterprise
- Network: Active Directory domain
- File system: NTFS

ROOT CAUSE:
The upgrade process failed to update the file cache path configuration.
The system was still pointing to the old network-mapped drive (C:)
which has slower performance than local SSD (D:).

RESOLUTION:
1. Open Creo preferences (File > Options)
2. Navigate to: General > Environment > File Cache Path
3. Change from: //network-server/cache/teamcenter
4. Change to: D:\\Creo_Cache (local SSD)
5. Restart Creo
6. Verify save operation works

VERIFICATION:
- Tested with 10 users
- All users can now save files successfully
- Performance improved by 40%
- No side effects observed

TECHNICAL DETAILS:
The Creo cache system maintains temporary files and compiled
metadata to improve performance. By default, it uses the system
drive, but can be configured to use faster storage.

PERFORMANCE METRICS:
- Before: Average save time = 3.2 seconds
- After: Average save time = 1.9 seconds
- Improvement: 40.6%

RELATED ISSUES:
- TKT-0042: Login timeout issues (unrelated)
- TKT-0043: License server performance (fixed in 11.0.2)

TESTED CONFIGURATIONS:
- Creo 11.0.0: VERIFIED
- Creo 11.0.1: VERIFIED
- Creo 10.0.12: VERIFIED (also affected, same fix applies)
"""
            
            with open(text_file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            logger.info(f"  ✓ Created sample RCA document: {text_file_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to create sample document: {e}")
            return False

    @staticmethod
    def process_rca_attachment(attachment_id: str, ticket_id: str, company_id: str) -> int:
        """
        Process an RCA (Root Cause Analysis) attachment.
        Extracts text, chunks it, and creates embeddings.
        
        Called when:
            AttachmentEvent.event_type = 'attachment_added'
            Attachment.type = 'rca'
        
        Args:
            attachment_id: UUID of the attachment
            ticket_id: UUID of the ticket
            company_id: UUID of the company
            
        Returns:
            Count of embeddings created
        """
        logger.info(f"Processing RCA attachment {attachment_id}...")
        count = 0
        db = SessionLocal()
        
        try:
            # Get attachment
            attachment = db.query(Attachment).filter(
                Attachment.id == attachment_id
            ).first()
            
            if not attachment:
                logger.error(f"Attachment not found: {attachment_id}")
                return 0
            
            if attachment.type != "rca":
                logger.warning(f"Attachment type is '{attachment.type}', not 'rca'")
                return 0
            
            logger.debug(f"  File path: {attachment.file_path}")
            logger.debug(f"  MIME type: {attachment.mime_type}")
            
            # Extract text based on file type
            text = AttachmentProcessor.extract_text_from_attachment(
                attachment.file_path,
                attachment.mime_type
            )
            
            if not text:
                logger.warning(f"Failed to extract text from {attachment.file_path}")
                return 0
            
            logger.info(f"  Extracted {len(text)} characters from attachment")
            
            # Chunk the text
            chunks = EmbeddingService.chunk_text(text)
            logger.info(f"  Split into {len(chunks)} chunks")
            
            # Create embeddings for each chunk
            for idx, chunk in enumerate(chunks):
                vector = EmbeddingService.get_embedding_vector(chunk)
                if vector:
                    emb = Embedding(
                        company_id=company_id,
                        ticket_id=ticket_id,
                        attachment_id=attachment_id,
                        source_type="rca",
                        chunk_index=idx,
                        text_content=chunk[:EmbeddingService.MAX_TEXT_LENGTH],
                        vector_id=str(uuid.uuid4()),
                        is_active=True
                    )
                    db.add(emb)
                    db.flush()
                    count += 1
                    logger.debug(f"    ✓ Created embedding {emb.id} (chunk {idx}/{len(chunks)})")
            
            db.commit()
            logger.info(f"✓ Processed RCA attachment {attachment_id}: {count} embeddings created")
            
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to process RCA attachment: {e}")
            return 0
        finally:
            db.close()
        
        return count
    
    @staticmethod
    def extract_text_from_attachment(file_path: str, mime_type: Optional[str] = None) -> Optional[str]:
        """
        Extract text from an attachment file.
        Supports PDF files and text files.
        
        Args:
            file_path: Path to the file (local or S3)
            mime_type: MIME type of the file (optional)
            
        Returns:
            Extracted text, or None if extraction failed
        """
        if not file_path:
            logger.error("File path is empty")
            return None
        
        logger.debug(f"Extracting text from: {file_path}")
        
        # Check if .txt version exists (for testing)
        actual_path = file_path
        if not os.path.exists(file_path) and file_path.lower().endswith('.pdf'):
            txt_version = file_path.replace('.pdf', '.txt')
            if os.path.exists(txt_version):
                actual_path = txt_version
                logger.debug(f"Using text version: {txt_version}")
        
        # Check if it's a PDF
        is_pdf = (mime_type and mime_type in AttachmentProcessor.PDF_MIME_TYPES) or \
                 file_path.lower().endswith('.pdf')
        
        if is_pdf and os.path.exists(file_path):
            return AttachmentProcessor.extract_text_from_pdf(file_path)
        
        # Try to read as plain text
        return AttachmentProcessor.extract_text_from_file(actual_path)
    
    @staticmethod
    def extract_text_from_pdf(file_path: str) -> Optional[str]:
        """
        Extract text from a PDF file.
        
        Args:
            file_path: Path to the PDF file
            
        Returns:
            Extracted text from all pages, or None if error
        """
        if not HAS_PDF:
            logger.error("PyPDF2 not installed. Cannot process PDF files.")
            logger.error("Install with: pip install PyPDF2")
            return None
        
        try:
            if not os.path.exists(file_path):
                logger.error(f"File not found: {file_path}")
                return None
            
            text_parts = []
            
            with open(file_path, 'rb') as f:
                pdf = PdfReader(f)
                total_pages = len(pdf.pages)
                logger.debug(f"  PDF has {total_pages} pages")
                
                for page_num, page in enumerate(pdf.pages):
                    try:
                        text = page.extract_text()
                        if text and text.strip():
                            text_parts.append(f"\n--- Page {page_num + 1} ---\n{text}")
                            logger.debug(f"    ✓ Extracted page {page_num + 1} ({len(text)} chars)")
                    except Exception as e:
                        logger.warning(f"  Failed to extract page {page_num + 1}: {e}")
            
            if not text_parts:
                logger.warning("No text could be extracted from PDF")
                return None
            
            result = "\n".join(text_parts)
            return result if result.strip() else None
            
        except Exception as e:
            logger.error(f"PDF extraction error: {e}")
            return None
    
    @staticmethod
    def extract_text_from_file(file_path: str) -> Optional[str]:
        """
        Extract text from a plain text file.
        
        Args:
            file_path: Path to the text file
            
        Returns:
            File contents, or None if error
        """
        try:
            if not os.path.exists(file_path):
                logger.error(f"File not found: {file_path}")
                return None
            
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                text = f.read()
                logger.debug(f"  Read {len(text)} characters")
                return text if text.strip() else None
                
        except Exception as e:
            logger.error(f"Text file extraction error: {e}")
            return None
    
    @staticmethod
    def replace_attachment(
        old_attachment_id: str,
        new_attachment_id: str,
        ticket_id: str,
        company_id: str,
        actor_user_id: str
    ) -> bool:
        """
        Replace an attachment with a newer version.
        Deprecates old embeddings and creates new ones.
        
        Called when:
            AttachmentEvent.event_type = 'attachment_replaced'
        
        Args:
            old_attachment_id: UUID of the old attachment
            new_attachment_id: UUID of the new attachment
            ticket_id: UUID of the ticket
            company_id: UUID of the company
            actor_user_id: UUID of the user making the change
            
        Returns:
            True if successful, False otherwise
        """
        logger.info(f"Replacing attachment {old_attachment_id} with {new_attachment_id}...")
        db = SessionLocal()
        
        try:
            # Deprecate old embeddings
            old_embeddings = db.query(Embedding).filter(
                Embedding.attachment_id == old_attachment_id,
                Embedding.is_active == True
            ).all()
            
            deprecated_count = 0
            for emb in old_embeddings:
                emb.is_active = False
                emb.deprecated_at = datetime.utcnow()
                emb.deprecation_reason = "attachment_replaced"
                deprecated_count += 1
            
            db.commit()
            logger.info(f"  ✓ Deprecated {deprecated_count} old embeddings")
            
            # Process new attachment
            new_count = AttachmentProcessor.process_rca_attachment(
                new_attachment_id,
                ticket_id,
                company_id
            )
            
            # Record the replacement event
            event = AttachmentEvent(
                ticket_id=ticket_id,
                attachment_id=new_attachment_id,
                event_type="attachment_replaced",
                actor_user_id=actor_user_id,
                payload={
                    "old_attachment_id": str(old_attachment_id),
                    "new_attachment_id": str(new_attachment_id),
                    "old_embeddings_deprecated": deprecated_count,
                    "new_embeddings_created": new_count
                }
            )
            db.add(event)
            db.commit()
            
            logger.info(f"✓ Attachment replacement complete")
            logger.info(f"  Old embeddings deprecated: {deprecated_count}")
            logger.info(f"  New embeddings created: {new_count}")
            
            return new_count > 0
            
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to replace attachment: {e}")
            return False
        finally:
            db.close()
    
    @staticmethod
    def deprecate_attachment(
        attachment_id: str,
        actor_user_id: str,
        reason: str = None
    ) -> bool:
        """
        Deprecate an attachment without replacing it.
        Marks all related embeddings as inactive.
        
        Called when:
            AttachmentEvent.event_type = 'attachment_deprecated'
        
        Args:
            attachment_id: UUID of the attachment to deprecate
            actor_user_id: UUID of the user making the change
            reason: Reason for deprecation (e.g., "incorrect_analysis")
            
        Returns:
            True if successful, False otherwise
        """
        logger.info(f"Deprecating attachment {attachment_id}...")
        db = SessionLocal()
        
        try:
            # Find and deprecate embeddings
            embeddings = db.query(Embedding).filter(
                Embedding.attachment_id == attachment_id,
                Embedding.is_active == True
            ).all()
            
            if not embeddings:
                logger.warning(f"No active embeddings found for attachment {attachment_id}")
                return False
            
            deprecated_count = 0
            for emb in embeddings:
                emb.is_active = False
                emb.deprecated_at = datetime.utcnow()
                emb.deprecation_reason = reason or "attachment_deprecated"
                deprecated_count += 1
            
            # Get attachment to find ticket ID
            attachment = db.query(Attachment).filter(
                Attachment.id == attachment_id
            ).first()
            
            # Record the deprecation event
            if attachment:
                event = AttachmentEvent(
                    ticket_id=attachment.ticket_id,
                    attachment_id=attachment_id,
                    event_type="attachment_deprecated",
                    actor_user_id=actor_user_id,
                    payload={
                        "reason": reason or "Manual deprecation",
                        "embeddings_deprecated": deprecated_count
                    }
                )
                db.add(event)
            
            db.commit()
            logger.info(f"✓ Deprecated {deprecated_count} embeddings for attachment")
            
            return True
            
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to deprecate attachment: {e}")
            return False
        finally:
            db.close()
    
    @staticmethod
    def get_attachment_info(attachment_id: str) -> dict:
        """
        Get information about an attachment and its embeddings.
        
        Args:
            attachment_id: UUID of the attachment
            
        Returns:
            Dict with attachment info and embedding counts
        """
        db = SessionLocal()
        try:
            attachment = db.query(Attachment).filter(
                Attachment.id == attachment_id
            ).first()
            
            if not attachment:
                return {"error": "Attachment not found"}
            
            embeddings = db.query(Embedding).filter(
                Embedding.attachment_id == attachment_id
            ).all()
            
            active_count = sum(1 for e in embeddings if e.is_active)
            inactive_count = sum(1 for e in embeddings if not e.is_active)
            
            return {
                "attachment_id": str(attachment_id),
                "ticket_id": str(attachment.ticket_id),
                "type": attachment.type,
                "file_path": attachment.file_path,
                "mime_type": attachment.mime_type,
                "created_at": to_iso_string(attachment.created_at),
                "total_embeddings": len(embeddings),
                "active_embeddings": active_count,
                "inactive_embeddings": inactive_count
            }
        finally:
            db.close()