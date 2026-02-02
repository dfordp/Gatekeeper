# server/services/attachment_processor.py
"""
Enhanced Attachment Processor Service with Grok Vision Integration

Handles attachment processing with:
- Grok Vision API for image/video understanding
- PDF text extraction
- Intelligent text chunking
- Embedding creation
- Event emission for async Qdrant sync

Usage:
    from services.attachment_processor import AttachmentProcessor
    
    # Process any attachment type
    count = AttachmentProcessor.process_attachment(
        attachment_id=attachment_id,
        ticket_id=ticket_id,
        company_id=company_id,
        mime_type=mime_type,
        ticket_subject=subject,
        ticket_description=description
    )
    
    # Deprecate attachment embeddings
    success = AttachmentProcessor.deprecate_attachment(
        attachment_id=attachment_id,
        reason="attachment_deleted"
    )
"""

import os
import sys
import logging
import base64
import requests
from typing import Optional, List
from datetime import datetime
from uuid import UUID
from pathlib import Path
from io import BytesIO

from core.database import SessionLocal, Attachment, Embedding
from core.config import GROQ_API_KEY
from core.logger import get_logger
from core.config import GROQ_API_KEY, VISION_MODEL
logger = get_logger(__name__)

# Try to import PDF library
try:
    from PyPDF2 import PdfReader
    HAS_PDF = True
except ImportError:
    HAS_PDF = False
    logger.warning("⚠ PyPDF2 not installed, PDF processing will not work")

# Grok API Configuration
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"


class AttachmentProcessor:
    """Enhanced service to process attachments with Grok vision integration"""
    
    # Configuration
    SUPPORTED_TYPES = ['rca', 'document', 'log', 'image', 'video']
    PDF_MIME_TYPES = ['application/pdf', 'application/x-pdf']
    IMAGE_MIME_TYPES = [
        'image/jpeg', 'image/jpg', 'image/png', 'image/gif', 'image/webp',
        'image/bmp', 'image/tiff', 'image/svg+xml'
    ]
    VIDEO_MIME_TYPES = [
        'video/mp4', 'video/mpeg', 'video/quicktime', 'video/webm',
        'video/x-msvideo', 'video/x-matroska'
    ]
    
    # Chunking configuration
    CHUNK_SIZE = 1500
    CHUNK_OVERLAP = 100
    MAX_TEXT_LENGTH = 2000
    
    @staticmethod
    def analyze_visual_content(
        file_path: str,
        mime_type: Optional[str] = None,
        ticket_context: Optional[str] = None
    ) -> Optional[str]:
        """
        Use Grok Vision API to understand images and videos.
        Analyzes visual content and returns text description.
        
        Args:
            file_path: Path to image/video file (local path or HTTPS URL)
            mime_type: MIME type of the file (e.g., 'image/jpeg')
            ticket_context: Optional ticket context for better analysis
            
        Returns:
            Text description of visual content, or None if analysis failed
        """
        if not GROQ_API_KEY:
            logger.warning("GROQ_API_KEY not set, skipping vision analysis")
            return None
        
        try:
            logger.info(f"Analyzing visual content with Grok: {file_path}")
            
            # Handle URLs directly (Cloudinary, etc.)
            if file_path.startswith(('http://', 'https://')):
                logger.debug(f"  Using URL source (no base64 encoding)")
                image_source = {
                    "type": "image_url",
                    "image_url": {"url": file_path}
                }
            else:
                # Local file - encode as base64
                if not os.path.exists(file_path):
                    logger.warning(f"Local file not found, skipping vision for: {file_path}")
                    return None
                
                # Determine media type
                if mime_type and mime_type.startswith('image/'):
                    media_type = mime_type
                elif mime_type and mime_type.startswith('video/'):
                    media_type = mime_type
                else:
                    ext = Path(file_path).suffix.lower()
                    ext_to_mime = {
                        '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png',
                        '.gif': 'image/gif', '.webp': 'image/webp', '.bmp': 'image/bmp',
                        '.tiff': 'image/tiff', '.svg': 'image/svg+xml',
                        '.mp4': 'video/mp4', '.webm': 'video/webm', '.mov': 'video/quicktime',
                    }
                    media_type = ext_to_mime.get(ext, 'image/jpeg')
                
                logger.debug(f"  Reading local file ({media_type})")
                with open(file_path, 'rb') as f:
                    file_data = f.read()
                    encoded = base64.standard_b64encode(file_data).decode('utf-8')
                
                image_source = {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{media_type};base64,{encoded}"
                    }
                }
            
            # Build system prompt
            system_prompt = (
                "You are an expert technical support analyst. Analyze the provided "
                "screenshot, diagram, error message, log output, or video frame. "
                "Provide a clear, concise technical description of what is shown."
            )
            
            if ticket_context:
                system_prompt += f"\n\nContext: {ticket_context}\nUse this context to provide more relevant analysis."
            
            # Call Grok Vision API
            logger.debug(f"  Calling Grok Vision API ({VISION_MODEL})...")
            response = requests.post(
                GROQ_API_URL,
                headers={
                    "Authorization": f"Bearer {GROQ_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": VISION_MODEL,
                    "messages": [
                        {
                            "role": "system",
                            "content": system_prompt
                        },
                        {
                            "role": "user",
                            "content": [
                                image_source,
                                {
                                    "type": "text",
                                    "text": (
                                        "Please provide a detailed technical description. "
                                        "Include: 1) What is shown, 2) Any text/errors visible, "
                                        "3) Relevant technical details, 4) Suggested next steps if applicable."
                                    )
                                }
                            ]
                        }
                    ],
                    "max_tokens": 1024
                },
                timeout=60
            )
            
            if response.status_code == 200:
                result = response.json()
                description = result.get('choices', [{}])[0].get('message', {}).get('content', '')
                
                if description and description.strip():
                    logger.info(f"✓ Vision analysis successful: {len(description)} chars")
                    return description
                else:
                    logger.warning("Vision API returned empty response")
                    return None
            else:
                error_msg = response.text[:200]
                logger.warning(f"Vision API error {response.status_code}: {error_msg}")
                return None
                
        except requests.Timeout:
            logger.warning("Vision API request timeout (60s)")
            return None
        except Exception as e:
            logger.warning(f"Vision analysis failed: {e}")
            return None
    
    @staticmethod
    def process_attachment(
        attachment_id: str,
        ticket_id: str,
        company_id: str,
        mime_type: Optional[str] = None,
        ticket_subject: Optional[str] = None,
        ticket_description: Optional[str] = None
    ) -> int:
        """
        Process any attachment type with vision and text extraction.
        Creates embeddings from extracted and analyzed content.
        
        Workflow:
        1. Retrieve attachment from database
        2. For images/videos: Use Grok Vision to extract description
        3. For PDFs/documents: Extract text
        4. Combine all text content
        5. Chunk text (1500 chars with 100 overlap)
        6. Create Embedding records for each chunk
        
        Args:
            attachment_id: UUID of the attachment
            ticket_id: UUID of the ticket
            company_id: UUID of the company
            mime_type: MIME type of file (e.g., 'image/png')
            ticket_subject: Ticket subject for vision context
            ticket_description: Ticket description for vision context
            
        Returns:
            Count of embeddings created (0 if failed or no content)
        """
        db = SessionLocal()
        try:
            # Get attachment record
            attachment = db.query(Attachment).filter(
                Attachment.id == UUID(attachment_id)
            ).first()
            
            if not attachment:
                logger.error(f"Attachment not found: {attachment_id}")
                return 0
            
            logger.info(f"Processing attachment {attachment_id}")
            logger.debug(f"  Type: {attachment.type}, MIME: {attachment.mime_type}")
            
            extracted_text = None
            visual_description = None
            
            # Step 1: Vision analysis for images and videos
            if attachment.mime_type in AttachmentProcessor.IMAGE_MIME_TYPES or \
               attachment.mime_type in AttachmentProcessor.VIDEO_MIME_TYPES:
                
                context = f"Ticket: {ticket_subject}" if ticket_subject else None
                
                visual_description = AttachmentProcessor.analyze_visual_content(
                    attachment.file_path,
                    attachment.mime_type,
                    context
                )
                
                # Step 5: Store visual analysis in metadata (if applicable)
                if visual_description:
                    try:
                        attachment.metadata = {
                            "visual_description": visual_description[:500],
                            "analysis_timestamp": datetime.utcnow().isoformat()
                        }
                        db.commit()
                        logger.debug(f"  ✓ Stored visual analysis metadata")
                    except Exception as e:
                        logger.warning(f"Failed to store metadata: {e}")
            
            # Step 2: Text extraction from PDFs and documents (for local files)
            if attachment.file_path and not attachment.file_path.startswith(('http://', 'https://')):
                extracted_text = AttachmentProcessor.extract_text_from_attachment(
                    attachment.file_path,
                    attachment.mime_type
                )
            
            # Step 3: Combine all content
            all_text = ""
            if visual_description:
                all_text += f"[VISUAL ANALYSIS]\n{visual_description}\n\n"
            if extracted_text:
                all_text += extracted_text
            
            if not all_text.strip():
                logger.warning(f"No content extracted from attachment {attachment_id}")
                return 0
            
            logger.info(f"  Total content: {len(all_text)} characters")
            
            # Step 4: Create embeddings from content
            count = AttachmentProcessor._create_embeddings(
                all_text,
                str(attachment.id),
                ticket_id,
                company_id,
                attachment.type
            )
            
            # Step 5: Store visual analysis in metadata (if applicable)
            if visual_description:
                try:
                    if not hasattr(attachment, 'metadata') or attachment.metadata is None:
                        attachment.metadata = {}
                    
                    attachment.metadata["visual_description"] = visual_description[:500]
                    attachment.metadata["analysis_timestamp"] = datetime.utcnow().isoformat()
                    db.commit()
                    logger.debug(f"  ✓ Stored visual analysis metadata")
                except Exception as e:
                    logger.warning(f"Failed to store metadata: {e}")
            
            logger.info(f"✓ Processed attachment {attachment_id}: {count} embeddings created")
            return count
            
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to process attachment: {e}")
            return 0
        finally:
            db.close()
    
    @staticmethod
    def _create_embeddings(
        text: str,
        attachment_id: str,
        ticket_id: str,
        company_id: str,
        attachment_type: str
    ) -> int:
        """
        Create and store embeddings from text content.
        Chunks text and creates Embedding database records with Qdrant sync.
        """
        logger.info(f"Starting embedding creation for attachment {attachment_id}")
        logger.info(f"  Text length: {len(text) if text else 0} characters")
        
        db = SessionLocal()
        count = 0
        synced_count = 0
        
        try:
            # Import here to avoid circular imports
            from .embedding_manager import EmbeddingManager
            
            # Chunk the text
            logger.info(f"  Chunking text (CHUNK_SIZE={AttachmentProcessor.CHUNK_SIZE}, OVERLAP={AttachmentProcessor.CHUNK_OVERLAP})")
            chunks = AttachmentProcessor._chunk_text(text)
            logger.info(f"  ✓ Split into {len(chunks)} chunks")
            
            if not chunks:
                logger.warning(f"No chunks created from text")
                return 0
            
            # Create embedding for each chunk
            logger.info(f"  Creating Embedding records for {len(chunks)} chunks...")
            for idx, chunk in enumerate(chunks):
                try:
                    if not chunk or not chunk.strip():
                        logger.debug(f"    Skipping empty chunk {idx+1}")
                        continue
                    
                    # Create embedding record without vector_id initially
                    emb = Embedding(
                        company_id=UUID(company_id),
                        ticket_id=UUID(ticket_id),
                        attachment_id=UUID(attachment_id),
                        source_type="log_snippet",
                        chunk_index=idx,
                        text_content=chunk[:AttachmentProcessor.MAX_TEXT_LENGTH],
                        is_active=True
                    )
                    db.add(emb)
                    db.flush()  # Get the embedding ID
                    
                    # Sync to Qdrant and set vector_id
                    point_id = EmbeddingManager._sync_embedding_to_qdrant(
                        db=db,
                        embedding_obj=emb,
                        ticket_id=ticket_id,
                        company_id=company_id,
                        source_type="log_snippet",
                        text_content=chunk
                    )
                    
                    if point_id:
                        synced_count += 1
                    
                    count += 1
                    logger.debug(f"    Added chunk {idx+1}/{len(chunks)} ({len(chunk)} chars)")
                    
                except Exception as e:
                    logger.warning(f"Failed to create embedding for chunk {idx}: {e}")
            
            # Commit all embeddings at once
            if count > 0:
                logger.info(f"  Committing {count} embeddings to database ({synced_count} synced to Qdrant)...")
                db.commit()
                logger.info(f"  ✓ Successfully committed {count} embeddings to database")
            else:
                logger.warning(f"No embeddings were created")
            
            return count
                
        except Exception as e:
            logger.error(f"Failed to create embeddings: {e}", exc_info=True)
            try:
                db.rollback()
                logger.info(f"Transaction rolled back")
            except Exception as rollback_error:
                logger.error(f"Rollback failed: {rollback_error}")
            return 0
        finally:
            db.close()
    
    @staticmethod
    def _chunk_text(text: str) -> List[str]:
        """Split text into overlapping chunks"""
        if not text:
            logger.warning("Empty text provided to _chunk_text")
            return []
        
        text_length = len(text)
        chunk_size = AttachmentProcessor.CHUNK_SIZE
        chunk_overlap = AttachmentProcessor.CHUNK_OVERLAP
        
        logger.info(f"_chunk_text: Processing {text_length} chars (size={chunk_size}, overlap={chunk_overlap})")
        
        # Single chunk case
        if text_length <= chunk_size:
            logger.info(f"_chunk_text: Text fits in single chunk, returning [1 chunk]")
            return [text]
        
        # Multiple chunks using range-based approach
        chunks = []
        start = 0
        
        logger.info(f"_chunk_text: Creating multiple chunks...")
        
        # Calculate chunk positions upfront
        positions = []
        pos = 0
        while pos < text_length:
            positions.append(pos)
            next_pos = pos + chunk_size
            if next_pos >= text_length:
                break
            pos = next_pos - chunk_overlap
        
        logger.info(f"_chunk_text: Calculated {len(positions)} chunk positions")
        
        # Now create chunks from positions
        for idx, start_pos in enumerate(positions, 1):
            end_pos = min(start_pos + chunk_size, text_length)
            chunk = text[start_pos:end_pos]
            chunks.append(chunk)
            logger.debug(f"_chunk_text: Chunk {idx}: [{start_pos}:{end_pos}] = {len(chunk)} chars")
        
        logger.info(f"_chunk_text: Complete - {len(chunks)} chunks from {text_length} chars")
        return chunks
    
    @staticmethod
    def extract_text_from_pdf(file_path: str) -> Optional[str]:
        """Extract text from a PDF file using PyPDF2"""
        if not HAS_PDF:
            logger.debug("PyPDF2 not installed, cannot process PDFs")
            return None
        
        try:
            if not os.path.exists(file_path):
                logger.debug(f"PDF file not found: {file_path}")
                return None
            
            logger.debug(f"Extracting text from PDF: {file_path}")
            text_parts = []
            
            with open(file_path, 'rb') as f:
                pdf = PdfReader(f)
                total_pages = len(pdf.pages)
                logger.debug(f"  PDF has {total_pages} pages")
                
                for page_num, page in enumerate(pdf.pages):
                    try:
                        text = page.extract_text()
                        if text and text.strip():
                            text_parts.append(f"--- Page {page_num + 1} ---\n{text}")
                            logger.debug(f"    ✓ Page {page_num + 1}: {len(text)} chars")
                    except Exception as e:
                        logger.warning(f"Failed to extract page {page_num + 1}: {e}")
            
            if not text_parts:
                logger.debug("No text extracted from PDF")
                return None
            
            result = "\n".join(text_parts)
            return result if result.strip() else None
            
        except Exception as e:
            logger.warning(f"PDF extraction error: {e}")
            return None
    
    @staticmethod
    def extract_text_from_file(file_path: str) -> Optional[str]:
        """Extract text from a plain text file"""
        try:
            if not os.path.exists(file_path):
                logger.debug(f"Text file not found: {file_path}")
                return None
            
            logger.debug(f"Reading text file: {file_path}")
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                text = f.read()
                logger.debug(f"  Read {len(text)} characters")
                return text if text.strip() else None
                
        except Exception as e:
            logger.warning(f"Text file extraction error: {e}")
            return None
    
    @staticmethod
    def deprecate_attachment(
        attachment_id: str,
        reason: Optional[str] = None
    ) -> bool:
        """Deprecate an attachment by marking its embeddings as inactive"""
        logger.info(f"Deprecating attachment {attachment_id}...")
        db = SessionLocal()
        
        try:
            embeddings = db.query(Embedding).filter(
                Embedding.attachment_id == UUID(attachment_id),
                Embedding.is_active == True
            ).all()
            
            if not embeddings:
                logger.debug(f"No active embeddings found for {attachment_id}")
                return True  # Still return True - nothing to deprecate is OK
            
            deprecation_reason = reason or "attachment_deprecated"
            now = datetime.utcnow()
            
            for emb in embeddings:
                emb.is_active = False
                emb.deprecated_at = now
                emb.deprecation_reason = deprecation_reason
            
            db.commit()
            logger.info(f"✓ Deprecated {len(embeddings)} embeddings (reason: {deprecation_reason})")
            return True
            
        except Exception as e:
            db.rollback()
            logger.warning(f"Failed to deprecate attachment: {e}")
            return False
        finally:
            db.close()

    @staticmethod
    def extract_text_from_attachment(
        file_path: str,
        mime_type: Optional[str] = None
    ) -> Optional[str]:
        """Extract text from local attachment file"""
        if not file_path:
            logger.error("File path is empty")
            return None
        
        # Skip URL-based files
        if file_path.startswith(('http://', 'https://')):
            logger.debug(f"Skipping URL-based file for text extraction: {file_path[:50]}...")
            return None
        
        logger.debug(f"Extracting text from: {file_path}")
        
        # Check for fallback txt version
        actual_path = file_path
        if not os.path.exists(file_path) and file_path.lower().endswith('.pdf'):
            txt_version = file_path.replace('.pdf', '.txt')
            if os.path.exists(txt_version):
                actual_path = txt_version
                logger.debug(f"Using text version: {txt_version}")
        
        # Detect if PDF
        is_pdf = (mime_type and mime_type in AttachmentProcessor.PDF_MIME_TYPES) or \
                 file_path.lower().endswith('.pdf')
        
        if is_pdf and os.path.exists(file_path):
            return AttachmentProcessor.extract_text_from_pdf(file_path)
        
        # Try as plain text
        return AttachmentProcessor.extract_text_from_file(actual_path)