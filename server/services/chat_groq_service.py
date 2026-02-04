# server/services/chat_groq_service.py
"""
Chat Groq Service - Intent extraction and vision analysis via Groq API

This service provides:
1. Intent extraction from user messages (no keywords, pure LLM)
2. Entity extraction (company context, issue type, etc.)
3. Image analysis via Groq Vision API
4. Confidence scoring
"""

import logging
import json
import re
from typing import Dict, List, Any, Optional, Tuple
from uuid import UUID
import base64
from datetime import datetime

from core.config import GROQ_API_KEY, VISION_MODEL, MODEL
from core.database import SessionLocal, Company, User

try:
    from groq import Groq
except ImportError:
    logging.warning("Groq SDK not installed. Install with: pip install groq")
    Groq = None

logger = logging.getLogger(__name__)


class ChatGroqService:
    """Service for intent extraction and vision analysis via Groq"""
    
    def __init__(self):
        if not GROQ_API_KEY:
            raise ValueError("GROQ_API_KEY not configured")
        self.client = Groq(api_key=GROQ_API_KEY)
        self.intent_model = MODEL
        self.vision_model = VISION_MODEL
    
    def extract_intent_and_data(
        self,
        user_message: str,
        company_id: UUID,
        user_id: UUID,
        conversation_history: Optional[List[Dict]] = None
    ) -> Dict[str, Any]:
        """
        Extract intent, entities, and context from user message.
        
        Returns structure:
        {
            "intent": "search_solution" | "create_ticket" | "get_status" | "report_issue",
            "confidence": 0-100,
            "entities": {
                "issue_description": str,
                "category": str,  # inferred
                "priority": str,  # inferred
                "issue_type": str
            },
            "requires_ticket": bool,
            "raw_response": str
        }
        """
        db = SessionLocal()
        try:
            # Get company and user context
            company = db.query(Company).filter(Company.id == company_id).first()
            user = db.query(User).filter(User.id == user_id).first()
            
            if not company or not user:
                raise ValueError("Company or user not found")
            
            # Build system prompt with company context
            system_prompt = f"""You are a helpful support ticket assistant for {company.name}.
            
Your user is {user.name} from the support team.

Your task is to analyze the user's message and extract:
1. The primary INTENT (one of: search_solution, create_ticket, get_status, report_issue)
2. CONFIDENCE in the intent (0-100)
3. KEY ENTITIES:
   - issue_description: What is the user trying to solve/report?
   - category: Inferred category (login-access, license, installation, upload-save, workflow, performance, integration, data-configuration, other)
   - priority: Inferred priority (critical, high, medium, low)
   - issue_type: Type of issue (bug, feature_request, documentation, other)

Respond ONLY with valid JSON (no markdown, no code blocks):
{{
    "intent": "...",
    "confidence": XX,
    "entities": {{
        "issue_description": "...",
        "category": "...",
        "priority": "...",
        "issue_type": "..."
    }},
    "reasoning": "..."
}}"""
            
            # Build conversation messages
            messages = []
            
            if conversation_history:
                messages.extend(conversation_history)
            
            messages.append({
                "role": "user",
                "content": user_message
            })
            
            # Call Groq API
            response = self.client.chat.completions.create(
                model=self.intent_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    *messages
                ],
                temperature=0.3,
                max_tokens=500
            )
            
            response_text = response.choices[0].message.content.strip()
            logger.info(f"Groq response: {response_text}")
            
            # Parse JSON response
            parsed = json.loads(response_text)
            
            return {
                "intent": parsed.get("intent", "search_solution"),
                "confidence": parsed.get("confidence", 50),
                "entities": parsed.get("entities", {}),
                "requires_ticket": parsed.get("intent") in ["create_ticket", "report_issue"],
                "raw_response": response_text
            }
        
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Groq response: {e}")
            return {
                "intent": "search_solution",
                "confidence": 30,
                "entities": {"issue_description": user_message},
                "requires_ticket": False,
                "error": "Failed to parse intent"
            }
        
        except Exception as e:
            logger.error(f"Error extracting intent: {e}")
            raise
        
        finally:
            db.close()
    
    def analyze_image(
        self,
        image_path: str,
        context: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Analyze image via Groq Vision API.
        
        Returns:
        {
            "description": str,
            "key_elements": List[str],
            "text_content": Optional[str],
            "error_or_issue": Optional[str],
            "raw_response": str
        }
        """
        try:
            # Read and encode image
            with open(image_path, "rb") as img_file:
                image_data = base64.standard_b64encode(img_file.read()).decode("utf-8")
            
            # Determine image type
            mime_type = "image/png" if image_path.lower().endswith(".png") else "image/jpeg"
            
            # Build prompt
            vision_prompt = "Analyze this image and describe what you see. "
            if context:
                vision_prompt += f"Context: {context}. "
            vision_prompt += "Identify any error messages, issues, or relevant information."
            
            # Call Groq Vision API
            response = self.client.chat.completions.create(
                model=self.vision_model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{mime_type};base64,{image_data}"
                                }
                            },
                            {
                                "type": "text",
                                "text": vision_prompt
                            }
                        ]
                    }
                ],
                temperature=0.3,
                max_tokens=1000
            )
            
            analysis = response.choices[0].message.content.strip()
            
            # Try to structure response
            return {
                "description": analysis,
                "key_elements": self._extract_key_elements(analysis),
                "text_content": self._extract_text_content(analysis),
                "error_or_issue": self._detect_issue(analysis),
                "raw_response": analysis
            }
        
        except Exception as e:
            logger.error(f"Error analyzing image: {e}")
            return {
                "description": "",
                "key_elements": [],
                "text_content": None,
                "error_or_issue": f"Failed to analyze image: {str(e)}",
                "raw_response": ""
            }
    
    @staticmethod
    def _extract_key_elements(text: str) -> List[str]:
        """Extract key elements from analysis"""
        # Simple heuristic: look for capitalized phrases
        elements = []
        sentences = text.split(". ")
        for sentence in sentences[:3]:  # First 3 sentences
            if sentence.strip():
                elements.append(sentence.strip())
        return elements
    
    @staticmethod
    def _extract_text_content(text: str) -> Optional[str]:
        """Extract any readable text from image analysis"""
        if "text" in text.lower() or "says" in text.lower() or "shows" in text.lower():
            return text
        return None
    
    @staticmethod
    def _detect_issue(text: str) -> Optional[str]:
        """Detect if analysis mentions an error or issue"""
        error_keywords = ["error", "failed", "issue", "problem", "crash", "bug", "exception", "warning"]
        text_lower = text.lower()
        for keyword in error_keywords:
            if keyword in text_lower:
                return f"Potential issue detected: {keyword}"
        return None