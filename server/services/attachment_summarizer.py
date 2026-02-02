# server/services/attachment_summarizer.py
"""
Attachment Summarizer Service

Analyzes attachments (images, PDFs, text) and generates concise summaries
using AI (Groq for images/videos, PyPDF2 for text extraction).

Workflow:
1. Identify attachment type (image, video, PDF, text)
2. Extract/analyze content (Grok Vision for images, PDF extraction, etc.)
3. Generate AI summary
4. Return summary + key points
"""

import logging
import sys
import os
import base64
import requests
from typing import Optional, Dict, Any, List
from pathlib import Path

from core.config import GROQ_API_KEY, VISION_MODEL, CLOUDINARY_CLOUD_NAME
from core.logger import get_logger

logger = get_logger(__name__)

try:
    from PyPDF2 import PdfReader
    HAS_PDF = True
except ImportError:
    HAS_PDF = False
    logger.warning("PyPDF2 not installed for PDF processing")


class AttachmentSummarizer:
    """Service to generate summaries for various attachment types"""
    
    # Configuration
    SUPPORTED_IMAGE_TYPES = {
        'image/jpeg', 'image/jpg', 'image/png', 'image/gif', 'image/webp',
        'image/bmp', 'image/tiff', 'image/svg+xml'
    }
    SUPPORTED_VIDEO_TYPES = {
        'video/mp4', 'video/mpeg', 'video/quicktime', 'video/webm',
        'video/x-msvideo', 'video/x-matroska'
    }
    SUPPORTED_PDF_TYPES = {
        'application/pdf', 'application/x-pdf'
    }
    SUPPORTED_TEXT_TYPES = {
        'text/plain', 'text/csv', 'text/html', 'application/json',
        'application/xml', 'text/xml'
    }
    
    # API endpoints
    GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
    GROQ_API_KEY = GROQ_API_KEY
    VISION_MODEL = VISION_MODEL
    
    # Limits
    MAX_SUMMARY_LENGTH = 300
    MAX_KEY_POINTS = 5
    MAX_PDF_PAGES = 20
    MAX_TEXT_EXTRACT = 5000
    
    @staticmethod
    def summarize_attachment(
        file_path: str,
        file_name: str,
        mime_type: str,
        ticket_context: Optional[str] = None,
        is_cloudinary_url: bool = False
    ) -> Dict[str, Any]:
        """
        Main method to summarize any attachment
        
        Args:
            file_path: Local path or Cloudinary URL
            file_name: Original filename
            mime_type: MIME type
            ticket_context: Optional ticket subject/description for context
            is_cloudinary_url: Whether file_path is a Cloudinary URL
            
        Returns:
            {
                "success": bool,
                "summary": str,
                "key_points": List[str],
                "confidence": float,
                "file_type": str,
                "processing_method": str,
                "error": Optional[str]
            }
        """
        logger.info(f"Summarizing attachment: {file_name} ({mime_type})")
        
        try:
            # Route to appropriate handler
            if mime_type in AttachmentSummarizer.SUPPORTED_IMAGE_TYPES:
                return AttachmentSummarizer._summarize_image(
                    file_path, file_name, ticket_context, is_cloudinary_url
                )
            
            elif mime_type in AttachmentSummarizer.SUPPORTED_VIDEO_TYPES:
                return AttachmentSummarizer._summarize_video(
                    file_path, file_name, ticket_context, is_cloudinary_url
                )
            
            elif mime_type in AttachmentSummarizer.SUPPORTED_PDF_TYPES:
                return AttachmentSummarizer._summarize_pdf(
                    file_path, file_name, ticket_context
                )
            
            elif mime_type in AttachmentSummarizer.SUPPORTED_TEXT_TYPES:
                return AttachmentSummarizer._summarize_text_file(
                    file_path, file_name, ticket_context
                )
            
            else:
                return {
                    "success": False,
                    "error": f"Unsupported file type: {mime_type}",
                    "file_type": "unknown"
                }
        
        except Exception as e:
            logger.error(f"Error summarizing attachment: {e}")
            return {
                "success": False,
                "error": str(e),
                "file_type": "unknown"
            }
    
    @staticmethod
    def _summarize_image(
        file_path: str,
        file_name: str,
        ticket_context: Optional[str] = None,
        is_cloudinary_url: bool = False
    ) -> Dict[str, Any]:
        """Summarize image using Grok Vision API"""
        
        if not AttachmentSummarizer.GROQ_API_KEY:
            logger.warning("GROQ_API_KEY not set, skipping image analysis")
            return {
                "success": False,
                "error": "Grok API not configured",
                "file_type": "image"
            }
        
        try:
            # Get image data
            if is_cloudinary_url:
                image_data = AttachmentSummarizer._fetch_image_from_url(file_path)
                if not image_data:
                    return {"success": False, "error": "Failed to fetch image", "file_type": "image"}
                image_base64 = base64.b64encode(image_data).decode('utf-8')
            else:
                image_base64 = AttachmentSummarizer._read_image_as_base64(file_path)
                if not image_base64:
                    return {"success": False, "error": "Failed to read image", "file_type": "image"}
            
            # Call Grok Vision API
            prompt = f"""Analyze this image and provide:
1. A brief summary (max 2 sentences)
2. Key observations (3-5 bullet points)

{f'Context: {ticket_context}' if ticket_context else ''}

Format your response as JSON:
{{
    "summary": "...",
    "key_points": ["...", "...", "..."],
    "confidence": 0.9
}}"""
            
            response = requests.post(
                AttachmentSummarizer.GROQ_API_URL,
                headers={
                    "Authorization": f"Bearer {AttachmentSummarizer.GROQ_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": AttachmentSummarizer.VISION_MODEL,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/jpeg;base64,{image_base64}"
                                    }
                                },
                                {
                                    "type": "text",
                                    "text": prompt
                                }
                            ]
                        }
                    ],
                    "max_tokens": 300
                },
                timeout=30
            )
            
            if response.status_code != 200:
                logger.error(f"Grok API error: {response.status_code} - {response.text}")
                return {
                    "success": False,
                    "error": f"Grok API error: {response.status_code}",
                    "file_type": "image"
                }
            
            # Parse response
            import json
            response_data = response.json()
            content = response_data['choices'][0]['message']['content']
            
            # Extract JSON from response
            try:
                result = json.loads(content)
                return {
                    "success": True,
                    "summary": result.get('summary', '')[:AttachmentSummarizer.MAX_SUMMARY_LENGTH],
                    "key_points": result.get('key_points', [])[:AttachmentSummarizer.MAX_KEY_POINTS],
                    "confidence": result.get('confidence', 0.8),
                    "file_type": "image",
                    "processing_method": "grok_vision"
                }
            except json.JSONDecodeError:
                # Try to extract manually
                return {
                    "success": True,
                    "summary": content[:AttachmentSummarizer.MAX_SUMMARY_LENGTH],
                    "key_points": [],
                    "confidence": 0.7,
                    "file_type": "image",
                    "processing_method": "grok_vision"
                }
        
        except Exception as e:
            logger.error(f"Error summarizing image: {e}")
            return {
                "success": False,
                "error": str(e),
                "file_type": "image"
            }
    
    @staticmethod
    def _summarize_video(
        file_path: str,
        file_name: str,
        ticket_context: Optional[str] = None,
        is_cloudinary_url: bool = False
    ) -> Dict[str, Any]:
        """Summarize video - extract first frame and analyze"""
        
        logger.info("Video summarization: extracting first frame")
        
        # For now, return placeholder (full video analysis requires ffmpeg)
        return {
            "success": True,
            "summary": f"Video file: {file_name}",
            "key_points": ["Video attachment", "Requires video processing service"],
            "confidence": 0.5,
            "file_type": "video",
            "processing_method": "metadata"
        }
    
    @staticmethod
    def _summarize_pdf(
        file_path: str,
        file_name: str,
        ticket_context: Optional[str] = None
    ) -> Dict[str, Any]:
        """Summarize PDF by extracting and analyzing text"""
        
        if not HAS_PDF:
            logger.warning("PyPDF2 not available for PDF processing")
            return {
                "success": False,
                "error": "PDF processing not available",
                "file_type": "pdf"
            }
        
        try:
            # Extract text from PDF
            extracted_text = AttachmentSummarizer._extract_pdf_text(file_path)
            
            if not extracted_text:
                return {
                    "success": False,
                    "error": "No text extracted from PDF",
                    "file_type": "pdf"
                }
            
            # Use Groq to summarize extracted text
            if AttachmentSummarizer.GROQ_API_KEY:
                return AttachmentSummarizer._summarize_with_groq(
                    extracted_text, "PDF document", ticket_context
                )
            else:
                # Fallback: manual summary
                key_points = extracted_text[:500].split('.')[:3]
                return {
                    "success": True,
                    "summary": extracted_text[:AttachmentSummarizer.MAX_SUMMARY_LENGTH],
                    "key_points": key_points,
                    "confidence": 0.6,
                    "file_type": "pdf",
                    "processing_method": "text_extraction"
                }
        
        except Exception as e:
            logger.error(f"Error summarizing PDF: {e}")
            return {
                "success": False,
                "error": str(e),
                "file_type": "pdf"
            }
    
    @staticmethod
    def _summarize_text_file(
        file_path: str,
        file_name: str,
        ticket_context: Optional[str] = None
    ) -> Dict[str, Any]:
        """Summarize text file"""
        
        try:
            text = AttachmentSummarizer._read_text_file(file_path)
            
            if not text:
                return {
                    "success": False,
                    "error": "No text in file",
                    "file_type": "text"
                }
            
            # Use Groq to summarize
            if AttachmentSummarizer.GROQ_API_KEY:
                return AttachmentSummarizer._summarize_with_groq(
                    text, "Text document", ticket_context
                )
            else:
                # Fallback
                key_points = text.split('.')[:3]
                return {
                    "success": True,
                    "summary": text[:AttachmentSummarizer.MAX_SUMMARY_LENGTH],
                    "key_points": key_points,
                    "confidence": 0.6,
                    "file_type": "text",
                    "processing_method": "text_extraction"
                }
        
        except Exception as e:
            logger.error(f"Error summarizing text file: {e}")
            return {
                "success": False,
                "error": str(e),
                "file_type": "text"
            }
    
    @staticmethod
    def _summarize_with_groq(
        content: str,
        content_type: str,
        ticket_context: Optional[str] = None
    ) -> Dict[str, Any]:
        """Use Groq API to summarize content"""
        
        try:
            prompt = f"""Summarize this {content_type}:

{content[:3000]}

{f'Ticket context: {ticket_context}' if ticket_context else ''}

Provide:
1. Brief summary (max 2 sentences)
2. Key points (3-5 bullet points)

Format as JSON:
{{
    "summary": "...",
    "key_points": ["...", "..."]
}}"""
            
            response = requests.post(
                AttachmentSummarizer.GROQ_API_URL,
                headers={
                    "Authorization": f"Bearer {AttachmentSummarizer.GROQ_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "llama-3.1-8b-instant-on_demand",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 300
                },
                timeout=30
            )
            
            if response.status_code != 200:
                logger.error(f"Groq API error: {response.status_code}")
                raise Exception(f"API error: {response.status_code}")
            
            import json
            response_data = response.json()
            message_content = response_data['choices'][0]['message']['content']
            
            try:
                result = json.loads(message_content)
                return {
                    "success": True,
                    "summary": result.get('summary', '')[:AttachmentSummarizer.MAX_SUMMARY_LENGTH],
                    "key_points": result.get('key_points', [])[:AttachmentSummarizer.MAX_KEY_POINTS],
                    "confidence": 0.85,
                    "file_type": content_type.lower(),
                    "processing_method": "groq_llm"
                }
            except json.JSONDecodeError:
                return {
                    "success": True,
                    "summary": message_content[:AttachmentSummarizer.MAX_SUMMARY_LENGTH],
                    "key_points": [],
                    "confidence": 0.75,
                    "file_type": content_type.lower(),
                    "processing_method": "groq_llm"
                }
        
        except Exception as e:
            logger.error(f"Groq summarization failed: {e}")
            raise
    
    # Helper methods
    
    @staticmethod
    def _read_image_as_base64(file_path: str) -> Optional[str]:
        """Read image file and return base64 encoded"""
        try:
            with open(file_path, 'rb') as f:
                return base64.b64encode(f.read()).decode('utf-8')
        except Exception as e:
            logger.error(f"Failed to read image: {e}")
            return None
    
    @staticmethod
    def _fetch_image_from_url(url: str) -> Optional[bytes]:
        """Fetch image from URL"""
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                return response.content
        except Exception as e:
            logger.error(f"Failed to fetch image from URL: {e}")
        return None
    
    @staticmethod
    def _extract_pdf_text(file_path: str) -> str:
        """Extract text from PDF"""
        try:
            text = ""
            with open(file_path, 'rb') as f:
                reader = PdfReader(f)
                # Read first N pages
                for page_num in range(min(AttachmentSummarizer.MAX_PDF_PAGES, len(reader.pages))):
                    page = reader.pages[page_num]
                    text += page.extract_text()
            
            return text[:AttachmentSummarizer.MAX_TEXT_EXTRACT]
        except Exception as e:
            logger.error(f"Failed to extract PDF text: {e}")
            return ""
    
    @staticmethod
    def _read_text_file(file_path: str) -> str:
        """Read text file"""
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                return f.read()[:AttachmentSummarizer.MAX_TEXT_EXTRACT]
        except Exception as e:
            logger.error(f"Failed to read text file: {e}")
            return ""