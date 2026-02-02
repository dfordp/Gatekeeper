# server/main.py
"""
Gatekeeper Support Platform - Main FastAPI Application

Integrates admin authentication, ticket management, and Telegram bot integration.
Features:
- JWT-based admin authentication
- Modular service architecture
- Telegram webhook integration
- Audit logging
- Semantic search and deduplication
"""

import os
import sys
import requests
import base64
import mimetypes
from enum import Enum
from datetime import datetime

# FastAPI
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

# Groq AI
from groq import Groq

# Core imports
from core.database import init_db, test_connection
from core.config import CORS_ORIGINS, TELEGRAM_TOKEN, TELEGRAM_API, GROQ_API_KEY, MODEL, VISION_MODEL
from core.logger import get_logger

# Middleware
from middleware.error_handler import register_error_handlers
from middleware.audit_middleware import audit_middleware

# Routes
from routes.auth_routes import router as auth_router
from routes.dashboard_routes import router as dashboard_router
from routes.user_routes import router as user_router
from routes.admin_routes import router as admin_routes_router
from routes.ticket_routes import router as ticket_routes_router
from routes.company_routes import router as company_routes_router
from routes.search_routes import router as search_router
from routes.rca_routes import router as rca_router

# Legacy session management (keeping for bot compatibility)
from session import (
    IssueCategory,
    get_or_create_session,
    clear_session,
    ValidationError,
    SUPPORTED_SOFTWARE
)

# Legacy agent functions
from agent_functions import (
    classify_issue_category,
    _confirm_and_create_ticket,
    _get_session_data,
    _get_available_options,
    _calculate_completeness
)

# Legacy prompts
from prompt import GATEKEEPER_PROMPT
from http_routes import http_router

# ==================== SETUP & CONFIGURATION ====================

logger = get_logger(__name__)

# Initialize Groq client
groq_client = Groq(api_key=GROQ_API_KEY)

# File size limits (in bytes)
MAX_IMAGE_SIZE = 5 * 1024 * 1024  # 5MB for images
MAX_VIDEO_SIZE = 20 * 1024 * 1024  # 20MB for videos

# Upload directory
UPLOADS_DIR = "uploads"
os.makedirs(UPLOADS_DIR, exist_ok=True)

# Conversation history (temporary, per session)
conversation_state: dict[int, list] = {}

# Validation
if not TELEGRAM_TOKEN:
    logger.warning("Missing TELEGRAM_BOT_TOKEN - Telegram bot will not work")
if not GROQ_API_KEY:
    logger.warning("Missing GROQ_API_KEY - AI features will not work")

# ==================== FASTAPI APPLICATION ====================

app = FastAPI(
    title="Gatekeeper Support Platform",
    description="Support ticket management system with semantic search, deduplication, and admin portal",
    version="2.0.0"
)

# ==================== MIDDLEWARE SETUP ====================

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Audit middleware for admin actions
app.middleware("http")(audit_middleware)

# ==================== ERROR HANDLERS ====================

register_error_handlers(app)

# ==================== ROUTE REGISTRATION ====================

# Authentication routes (Phase 1)
app.include_router(auth_router)
app.include_router(dashboard_router)
app.include_router(user_router)
app.include_router(admin_routes_router)
app.include_router(ticket_routes_router)
app.include_router(company_routes_router)
app.include_router(search_router)
app.include_router(rca_router)


# Legacy HTTP routes (existing bot)
app.include_router(http_router)

# Additional routers will be registered here as they're created
# - Ticket routes (Phase 3)
# - Import routes (Phase 2)
# - RCA routes (Phase 6)
# - Analytics routes (Phase 3)

# ==================== TELEGRAM HELPER FUNCTIONS ====================

def send_message(chat_id: int, text: str) -> bool:
    """
    Send message to Telegram chat.
    
    Args:
        chat_id: Telegram chat ID
        text: Message text
        
    Returns:
        True if successful, False otherwise
    """
    if not text or not text.strip():
        return False
    
    if not TELEGRAM_TOKEN:
        logger.warning("Telegram token not configured")
        return False
    
    try:
        resp = requests.post(
            f"{TELEGRAM_API}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=5
        )
        return resp.status_code == 200
    except Exception as e:
        logger.error(f"Telegram send failed for chat {chat_id}: {e}")
        return False


async def download_file(file_id: str, file_name: str, max_size: int = None) -> str | None:
    """
    Download file from Telegram.
    
    Args:
        file_id: Telegram file ID
        file_name: Local file name
        max_size: Optional max file size in bytes
        
    Returns:
        Local file path if successful, None otherwise
    """
    if not TELEGRAM_TOKEN:
        return None
    
    try:
        meta = requests.get(
            f"{TELEGRAM_API}/getFile",
            params={"file_id": file_id},
            timeout=5
        ).json()

        if not meta.get("ok"):
            return None

        file_path = meta["result"]["file_path"]
        file_size = meta["result"].get("file_size", 0)
        
        # Check file size limit
        if max_size and file_size > max_size:
            logger.warning(f"File {file_name} exceeds size limit: {file_size} > {max_size}")
            return None

        url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_path}"
        content = requests.get(url, timeout=10)

        if content.status_code == 200:
            safe_name = os.path.basename(file_name)
            local_path = os.path.join(UPLOADS_DIR, safe_name)
            
            with open(local_path, "wb") as f:
                f.write(content.content)
            
            logger.info(f"Downloaded file: {local_path}")
            return local_path
        else:
            return None

    except Exception as e:
        logger.error(f"File download failed: {e}")
        return None


async def analyze_image_with_vision(image_path: str, chat_id: int) -> str | None:
    """
    Analyze image using Groq's vision API.
    
    Args:
        image_path: Path to local image file
        chat_id: Telegram chat ID for logging
        
    Returns:
        Analysis text or None if failed
    """
    if not GROQ_API_KEY:
        logger.warning("OpenAI API key not configured")
        return None
    
    try:
        # Read image and encode to base64
        with open(image_path, "rb") as f:
            image_data = base64.b64encode(f.read()).decode('utf-8')
        
        # Determine media type
        mime_type, _ = mimetypes.guess_type(image_path)
        if not mime_type:
            mime_type = "image/jpeg"
        
        # Create data URL for base64 image
        data_url = f"data:{mime_type};base64,{image_data}"
        
        # Call vision API
        response = groq_client.chat.completions.create(
            model=VISION_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": """Analyze this screenshot and identify:
1. What application or system is shown?
2. What error messages or status indicators are visible?
3. What is the user trying to do?
4. What appears to be wrong or blocked?

Be specific and factual. Only describe what you see, don't speculate."""
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": data_url,
                            },
                        }
                    ],
                }
            ],
            max_tokens=300,
            temperature=0.2
        )
        
        analysis = response.choices[0].message.content.strip()
        logger.info(f"[{chat_id}] Image analysis complete")
        return analysis
    
    except Exception as e:
        logger.error(f"[{chat_id}] Vision API failed: {e}")
        return None


async def extract_info_from_image_analysis(chat_id: int, analysis_text: str, session) -> None:
    """
    Extract structured information from image analysis.
    
    Args:
        chat_id: Telegram chat ID
        analysis_text: Image analysis from vision API
        session: User session object
    """
    if not analysis_text.strip() or not GROQ_API_KEY:
        return
    
    try:
        available_options = _get_available_options()
        
        # Use LLM to extract structured data from vision analysis
        response = groq_client.chat.completions.create(
            model=MODEL,
            messages=[
                {
                    "role": "user",
                    "content": f"""From this image analysis, extract ONLY these fields if mentioned.
IMPORTANT: Only use EXACT values from the valid options below. Do NOT invent or paraphrase values.

=== VALID OPTIONS ===
Software: {', '.join(available_options['software'])}
Environments: {', '.join(available_options['environments'])}
Impact Levels: {', '.join(available_options['impact_levels'])}

=== EXTRACTION TASK ===
Extract these fields from the analysis if visible:
1. Software: EXACT software name from the list above
2. Error: Error message or code (alphanumeric and spaces only)
3. Environment: MUST be EXACTLY one of: {', '.join(available_options['environments'])}
4. Impact: MUST be EXACTLY one of: {', '.join(available_options['impact_levels'])}

Image Analysis:
{analysis_text}

Respond ONLY with found fields in format: field: value (one per line)
Example:
Software: Teamcenter
Error: Connection timeout
Environment: Production
Impact: Completely blocked

If field not found, do NOT include it."""
                }
            ],
            max_tokens=200,
            temperature=0.1
        )
        
        extracted_data = response.choices[0].message.content
        logger.info(f"[{chat_id}] Vision extraction output:\n{extracted_data}")
        
        # Parse and apply extracted information
        lines = extracted_data.split('\n')
        for line in lines:
            if not line.strip() or ':' not in line:
                continue
            
            try:
                field, value = line.split(':', 1)
                field = field.strip().lower()
                value = value.strip()
                
                if not value:
                    continue
                
                # Software extraction
                if not session.software and 'software' in field:
                    value_lower = value.lower()
                    for keyword, software_name in SUPPORTED_SOFTWARE.items():
                        if keyword in value_lower:
                            try:
                                session.software = software_name
                                logger.info(f"[{chat_id}] Vision: Applied software = {software_name}")
                            except ValidationError as e:
                                logger.warning(f"[{chat_id}] Vision: Failed to apply software: {e}")
                            break
                
                # Environment extraction
                elif not session.environment and 'environment' in field:
                    valid_envs = available_options['environments']
                    for env_option in valid_envs:
                        if value.lower() == env_option.lower():
                            try:
                                session.environment = env_option
                                logger.info(f"[{chat_id}] Vision: Applied environment = {env_option}")
                            except ValidationError as e:
                                logger.warning(f"[{chat_id}] Vision: Failed to apply environment: {e}")
                            break
                
                # Impact extraction
                elif not session.impact and 'impact' in field:
                    if any(kw in value.lower() for kw in ['completely', 'fully', 'blocked', 'unable']):
                        try:
                            session.impact = "Completely blocked"
                            logger.info(f"[{chat_id}] Vision: Applied impact = Completely blocked")
                        except ValidationError as e:
                            logger.warning(f"[{chat_id}] Vision: Failed to apply impact: {e}")
                    elif any(kw in value.lower() for kw in ['partial', 'some']):
                        try:
                            session.impact = "Partially blocked"
                            logger.info(f"[{chat_id}] Vision: Applied impact = Partially blocked")
                        except ValidationError as e:
                            logger.warning(f"[{chat_id}] Vision: Failed to apply impact: {e}")
                    elif any(kw in value.lower() for kw in ['slow', 'sluggish', 'lag', 'usable']):
                        try:
                            session.impact = "Slow but usable"
                            logger.info(f"[{chat_id}] Vision: Applied impact = Slow but usable")
                        except ValidationError as e:
                            logger.warning(f"[{chat_id}] Vision: Failed to apply impact: {e}")
                
                # Issue description
                elif not session.issue_description and 'error' in field and value:
                    cleaned_value = ''.join(c if c.isalnum() or c in ' .-_:' else '' for c in value)
                    if cleaned_value.strip():
                        try:
                            session.issue_description = f"Error: {cleaned_value[:100]}"
                            session.issue_category = classify_issue_category(cleaned_value)
                            logger.info(f"[{chat_id}] Vision: Applied issue = {cleaned_value[:50]}...")
                        except ValidationError as e:
                            logger.warning(f"[{chat_id}] Vision: Failed to apply issue: {e}")
            
            except Exception as e:
                logger.warning(f"[{chat_id}] Vision: Error parsing line '{line}': {e}")
                continue
    
    except Exception as e:
        logger.error(f"[{chat_id}] Info extraction from analysis failed: {e}")


# ==================== DATA EXTRACTION ====================

async def try_extract_field(chat_id: int, text: str, session) -> tuple[bool, str | None]:
    """
    Try to extract and save a single field from user input.
    
    Args:
        chat_id: Telegram chat ID
        text: User input text
        session: User session object
        
    Returns:
        Tuple of (success, field_name_saved)
    """
    t = text.lower().strip()
    
    if not text or not t:
        return False, None
    
    # Software (check FIRST before other patterns)
    if not session.software:
        text_lower = text.lower()
        for keyword, software_name in SUPPORTED_SOFTWARE.items():
            if keyword in text_lower:
                try:
                    session.software = software_name
                    return True, "software"
                except ValidationError:
                    return False, None
    
    # Impact level
    if not session.impact:
        if any(w in t for w in ['completely', 'fully', 'fully blocked', 'unable to work', 'blocked']):
            try:
                session.impact = "Completely blocked"
                return True, "impact"
            except ValidationError:
                return False, None
        
        elif any(w in t for w in ['partial', 'partially', 'some features']):
            try:
                session.impact = "Partially blocked"
                return True, "impact"
            except ValidationError:
                return False, None
        
        elif any(w in t for w in ['slow', 'sluggish', 'usable', 'slower', 'laggy']):
            try:
                session.impact = "Slow but usable"
                return True, "impact"
            except ValidationError:
                return False, None
    
    # Issue description
    if not session.issue_description:
        issue_keywords = [
            'unable', "can't", 'cannot', 'problem', 'issue', 'error',
            'slow', 'blocked', 'crash', 'not working', 'broken', 'failed'
        ]
        
        is_long = len(text) > 15
        has_keyword = any(kw in t for kw in issue_keywords)
        
        if is_long or has_keyword:
            try:
                session.issue_description = text
                session.issue_category = classify_issue_category(text)
                return True, "issue_description"
            except ValidationError:
                return False, None
    
    # Name + Company
    if not session.user_name:
        parts = [p.strip() for p in text.split(",")]
        if len(parts) >= 2 and 2 < len(parts[0]) < 50 and 2 < len(parts[1]) < 100:
            try:
                session.user_name = parts[0]
                session.company_name = parts[1]
                return True, "user_name"
            except ValidationError:
                return False, None
    
    # Just user name
    if not session.user_name and 2 < len(text) < 50:
        is_issue = any(kw in t for kw in ['unable', 'problem', 'error', 'slow', 'blocked'])
        is_env = any(kw in t for kw in ['prod', 'test', 'local', 'uat'])
        is_impact = any(kw in t for kw in ['completely', 'partial', 'slow', 'usable'])
        
        if not is_issue and not is_env and not is_impact:
            try:
                session.user_name = text
                return True, "user_name"
            except ValidationError:
                return False, None
    
    # Company name
    if not session.company_name and session.user_name and 2 < len(text) < 100:
        try:
            session.company_name = text
            return True, "company_name"
        except ValidationError:
            return False, None
    
    # Environment
    if not session.environment:
        env_keywords = {
            'prod': 'Production',
            'production': 'Production',
            'uat': 'Test / UAT',
            'test': 'Test / UAT',
            'local': 'Local system',
        }
        
        for kw, env_val in env_keywords.items():
            if kw in t:
                try:
                    session.environment = env_val
                    return True, "environment"
                except ValidationError:
                    return False, None
    
    return False, None


async def generate_summary(session) -> str:
    """
    Generate summary of collected information.
    
    Args:
        session: User session object
        
    Returns:
        Formatted summary string
    """
    summary = "📋 Here's what I've collected:\n\n"
    summary += f"1️⃣ Name: {session.user_name}\n"
    summary += f"2️⃣ Company: {session.company_name}\n"
    summary += f"3️⃣ Software: {session.software}\n"
    
    env_display = session.environment.value if session.environment and isinstance(session.environment, Enum) else session.environment
    summary += f"4️⃣ Environment: {env_display}\n"
    
    cat_display = session.issue_category.value if session.issue_category and isinstance(session.issue_category, Enum) else session.issue_category
    summary += f"5️⃣ Category: {cat_display}\n"
    
    impact_display = session.impact.value if session.impact and isinstance(session.impact, Enum) else session.impact
    summary += f"6️⃣ Impact: {impact_display}\n"
    
    summary += f"7️⃣ Issue: {session.issue_description}\n"
    
    if session.attachments:
        summary += f"📎 Attachments: {len(session.attachments)} file(s)\n"
    
    summary += "\n✏️ Edit any field: reply 'edit 1-7' (e.g., 'edit 2' to change company)\n"
    summary += "✅ Or reply YES to create the ticket."
    return summary


async def process_pre_confirmation_edit(chat_id: int, edit_request: str, session) -> str:
    """
    Handle edit request before ticket confirmation.
    
    Args:
        chat_id: Telegram chat ID
        edit_request: Edit field request
        session: User session object
        
    Returns:
        Response message
    """
    field_map = {
        '1': ('user_name', 'Name'),
        '2': ('company_name', 'Company'),
        '3': ('software', 'Software'),
        '4': ('environment', 'Environment'),
        '5': ('issue_category', 'Category'),
        '6': ('impact', 'Impact'),
        '7': ('issue_description', 'Issue Description'),
        'name': ('user_name', 'Name'),
        'company': ('company_name', 'Company'),
        'software': ('software', 'Software'),
        'environment': ('environment', 'Environment'),
        'category': ('issue_category', 'Category'),
        'impact': ('impact', 'Impact'),
        'issue': ('issue_description', 'Issue Description'),
    }
    
    if edit_request not in field_map:
        return "❌ Invalid field. Use 1-7 or field name"
    
    attr_name, display_name = field_map[edit_request]
    current_value = getattr(session, attr_name, None)
    
    session.edit_field_mode = True
    session.edit_field_name = attr_name
    session.edit_field_display = display_name
    
    return f"✏️ Editing {display_name}\nCurrent value: {current_value}\n\nWhat should the new value be?"


async def apply_pre_confirmation_edit(chat_id: int, new_value: str, session) -> str:
    """
    Apply edited value to session.
    
    Args:
        chat_id: Telegram chat ID
        new_value: New field value
        session: User session object
        
    Returns:
        Response message
    """
    if not hasattr(session, 'edit_field_name') or not session.edit_field_name:
        return "❌ No field in edit mode. Use 'edit 1-7' first."
    
    attr_name = session.edit_field_name
    display_name = session.edit_field_display
    
    try:
        if attr_name == 'user_name':
            session.user_name = new_value
            validated_value = session.user_name
        elif attr_name == 'company_name':
            session.company_name = new_value
            validated_value = session.company_name
        elif attr_name == 'software':
            session.software = new_value
            validated_value = session.software
        elif attr_name == 'environment':
            session.environment = new_value
            validated_value = session.environment.value if hasattr(session.environment, 'value') else session.environment
        elif attr_name == 'issue_category':
            category_matched = None
            for cat in IssueCategory:
                if new_value.lower() in cat.value.lower():
                    session.issue_category = cat
                    category_matched = cat.value
                    break
            if not category_matched:
                return f"❌ Invalid category."
            validated_value = category_matched
        elif attr_name == 'impact':
            session.impact = new_value
            validated_value = session.impact.value if hasattr(session.impact, 'value') else session.impact
        elif attr_name == 'issue_description':
            session.issue_description = new_value
            session.issue_category = classify_issue_category(new_value)
            validated_value = session.issue_description
        else:
            return f"❌ Unknown field: {attr_name}"
        
        session.edit_field_mode = False
        session.edit_field_name = None
        session.edit_field_display = None
        
        summary = await generate_summary(session)
        return f"✅ {display_name} updated to: {validated_value}\n\n{summary}"
    
    except ValidationError as e:
        return f"❌ Validation error: {str(e)}"
    except Exception as e:
        logger.error(f"[{chat_id}] Edit error: {e}")
        return f"❌ Error updating field: {str(e)}"


# ==================== LLM INTEGRATION ====================

async def run_llm(chat_id: int, user_text: str) -> str:
    """
    Run LLM conversation for ticket intake.
    
    Args:
        chat_id: Telegram chat ID
        user_text: User message
        
    Returns:
        LLM response message
    """
    if not GROQ_API_KEY:
        return "AI features not configured. Please contact administrator."
    
    session = get_or_create_session(chat_id)
    history = conversation_state.get(chat_id, [])
    
    # Silent field extraction
    await try_extract_field(chat_id, user_text, session)
    
    # Get completeness status
    completeness = _calculate_completeness(session)
    all_collected = completeness['collected'] == completeness['total']
    
    # ========== STEP 1: SUMMARY ALREADY SHOWN ==========
    if session.summary_shown and not session.ticket_created:
        user_lower = user_text.lower().strip()
        
        if hasattr(session, 'edit_field_mode') and session.edit_field_mode:
            return await apply_pre_confirmation_edit(chat_id, user_text, session)
        
        if user_lower.startswith('edit '):
            edit_request = user_lower[5:].strip()
            return await process_pre_confirmation_edit(chat_id, edit_request, session)
        
        confirmation_keywords = ['yes', 'yep', 'y', 'confirm', 'ok', 'okey', 'correct', 'right', 'true', 'okay']
        user_says_yes = any(kw in user_lower for kw in confirmation_keywords)
        
        if user_says_yes:
            result = await _confirm_and_create_ticket(True, chat_id=chat_id)
            
            if result.get("ok"):
                ticket_id = result.get('ticket_id')
                reply = (
                    f"✅ Ticket created successfully!\n"
                    f"Ticket ID: {ticket_id}\n\n"
                    f"Our support team will review this and get back to you shortly."
                )
                
                clear_session(chat_id)
                conversation_state.pop(chat_id, None)
                
                return reply
            else:
                error_msg = result.get("error", "Unknown error")
                reply = f"Sorry, I couldn't create the ticket: {error_msg}"
                send_message(chat_id, reply)
                return reply
        else:
            summary = await generate_summary(session)
            return summary
    
    # ========== STEP 2: ALL DATA COLLECTED - SHOW SUMMARY ==========
    if all_collected and not session.summary_shown and not session.ticket_created:
        session.summary_shown = True
        summary = await generate_summary(session)
        return summary
    
    # ========== STEP 3: CONTINUE COLLECTING DATA VIA LLM ==========
    available_options = _get_available_options()
    session_data = await _get_session_data(chat_id=chat_id)
    
    session_context = f"""
=== CURRENT SESSION STATE ===
User Name: {session_data.get('user_name') or '[not provided]'}
Company: {session_data.get('company_name') or '[not provided]'}
Issue Description: {session_data.get('issue_description') or '[not provided]'}
Issue Category: {session_data.get('issue_category') or '[not provided]'}
Software/System: {session_data.get('software') or '[not provided]'}
Environment: {session_data.get('environment') or '[not provided]'}
Impact Level: {session_data.get('impact') or '[not provided]'}
Attachments: {session_data.get('attachments_count', 0)} file(s)

=== PROGRESS ===
Collected: {completeness['collected']}/{completeness['total']} fields ({completeness['percentage']:.0f}%)
Missing: {', '.join(completeness['missing_fields']) if completeness['missing_fields'] else 'None'}

=== VALID OPTIONS ===
Environments: {', '.join(available_options['environments'])}
Impact Levels: {', '.join(available_options['impact_levels'])}
Software: {', '.join(available_options['software'])}

=== CRITICAL INSTRUCTIONS ===
1. ONLY ASK ONE QUESTION to collect missing fields
2. Ask for missing fields ONLY (do not repeat)
3. NEVER create a summary - system handles that
4. NEVER hallucinate data
5. Keep responses short (1-2 sentences)
6. Acknowledge briefly before asking the next question
7. Do not ask about attachments - system handles uploads
"""
    
    messages = [
        {"role": "system", "content": GATEKEEPER_PROMPT + session_context},
        *history,
        {"role": "user", "content": user_text}
    ]
    
    try:
        resp = groq_client.chat.completions.create(
            model=MODEL,
            messages=messages,
            temperature=0.35,
            max_tokens=250,
            top_p=0.95
        )
        
        reply = (resp.choices[0].message.content or "").strip()
        
        if not reply:
            reply = "Could you tell me a bit more about what you're experiencing?"
        
        # Filter LLM-generated summaries
        summary_indicators = [
            'issue category:', 'system and environment:', 'impact level:',
            'here\'s', 'summary:', '1.', '2.', '3.',
            'got it', 'thanks', 'understood', 'correct?'
        ]
        
        is_summary_attempt = (
            any(indicator in reply.lower() for indicator in summary_indicators) and
            ':' in reply
        )
        
        if is_summary_attempt:
            logger.warning(f"[{chat_id}] LLM attempted to generate summary, filtering it out")
            
            if completeness['missing_fields']:
                next_field = completeness['missing_fields'][0]
                question_map = {
                    'user_name': "What's your full name?",
                    'company_name': "What company do you work for?",
                    'issue_description': "Can you describe the issue you're experiencing?",
                    'software': "Which software or system is affected?",
                    'environment': "Where are you experiencing this issue (Production, Test/UAT, or Local)?",
                    'issue_category': "What category best describes this issue?",
                    'impact': "How much are you blocked (completely, partially, or just slow)?",
                }
                reply = question_map.get(next_field, f"Tell me more about {next_field}")
    
    except Exception as e:
        logger.error(f"LLM error: {e}")
        reply = "Sorry, something went wrong. Please try again."
    
    # Store conversation history
    conversation_state[chat_id] = (
        history
        + [{"role": "user", "content": user_text}]
        + [{"role": "assistant", "content": reply}]
    )[-10:]
    
    return reply


async def process_file_with_text(chat_id: int, file_path: str, file_name: str, text: str, session) -> None:
    """
    Process file attachment along with text message.
    
    Args:
        chat_id: Telegram chat ID
        file_path: Local file path
        file_name: Original file name
        text: Accompanying text
        session: User session object
    """
    file_ext = os.path.splitext(file_name)[1].lower()
    
    # Analyze image with vision if it's an image
    if file_ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']:
        analysis = await analyze_image_with_vision(file_path, chat_id)
        if analysis:
            await extract_info_from_image_analysis(chat_id, analysis, session)
    
    # Also extract from the text if provided
    if text and text.strip():
        await try_extract_field(chat_id, text, session)


# ==================== TELEGRAM WEBHOOK ====================

@app.post("/telegram/webhook")
async def telegram_webhook(req: Request):
    """
    Handle incoming Telegram webhook.
    
    Processes messages, files, and commands from Telegram bot.
    """
    try:
        data = await req.json()
    except Exception as e:
        logger.error(f"Failed to parse webhook: {e}")
        return {"ok": False}
    
    msg = data.get("message")
    if not msg:
        return {"ok": True}
    
    chat_id = msg["chat"]["id"]
    
    try:
        session = get_or_create_session(chat_id)
        
        # Get text if present
        text = msg.get("text", "").strip() if "text" in msg else ""
        caption = msg.get("caption", "").strip() if "caption" in msg else ""
        user_input = text or caption
        
        # File upload (document)
        if "document" in msg:
            file_name = msg["document"].get("file_name", "document")
            path = await download_file(msg["document"]["file_id"], file_name, max_size=MAX_IMAGE_SIZE)
            if path:
                session.attachments.append(path)
                await process_file_with_text(chat_id, path, file_name, user_input, session)
                
                if user_input:
                    reply = await run_llm(chat_id, user_input)
                    send_message(chat_id, reply)
                else:
                    send_message(chat_id, "📎 Got the file. Please continue.")
            else:
                send_message(chat_id, "❌ Failed to download file. File may be too large (max 5MB).")
            return {"ok": True}
        
        # Photo upload
        if "photo" in msg:
            photo = msg["photo"][-1]
            path = await download_file(photo["file_id"], f"screenshot_{chat_id}_{len(session.attachments)}.jpg", max_size=MAX_IMAGE_SIZE)
            if path:
                session.attachments.append(path)
                await process_file_with_text(chat_id, path, f"screenshot.jpg", user_input, session)
                
                if user_input:
                    reply = await run_llm(chat_id, user_input)
                    send_message(chat_id, reply)
                else:
                    send_message(chat_id, "📸 Got the screenshot. Please continue.")
            else:
                send_message(chat_id, "❌ Failed to download screenshot. File may be too large (max 5MB).")
            return {"ok": True}
        
        # Video upload
        if "video" in msg:
            video = msg["video"]
            video_name = f"video_{chat_id}_{len(session.attachments)}.mp4"
            path = await download_file(video["file_id"], video_name, max_size=MAX_VIDEO_SIZE)
            if path:
                session.attachments.append(path)
                if user_input:
                    await try_extract_field(chat_id, user_input, session)
                
                if user_input:
                    reply = await run_llm(chat_id, user_input)
                    send_message(chat_id, reply)
                else:
                    send_message(chat_id, "🎥 Got the video. Please continue.")
            else:
                send_message(chat_id, "❌ Failed to download video. File may be too large (max 20MB).")
            return {"ok": True}
        
        if user_input:
            # Special commands
            if user_input.lower() in ["/start", "/help"]:
                greeting = (
                    "Hi! I'm Gatekeeper, your support intake assistant.\n\n"
                    "I'll help you create a support ticket by asking a few quick questions.\n"
                    "You can also upload screenshots or videos to help explain your issue.\n"
                    "Use /edit <ticket_id> to modify an existing ticket.\n"
                    "Please describe your issue, and I'll guide you from there."
                )
                send_message(chat_id, greeting)
                return {"ok": True}
            
            if user_input.lower().startswith("/edit "):
                ticket_id = user_input[6:].strip().upper()
                if not ticket_id:
                    send_message(chat_id, "Usage: /edit <ticket_id>")
                    return {"ok": True}
                
                # Show ticket for editing
                send_message(chat_id, f"Edit feature coming in Phase 2 - editing ticket {ticket_id}")
                return {"ok": True}
            
            if user_input.lower() == "/cancel":
                clear_session(chat_id)
                conversation_state.pop(chat_id, None)
                send_message(chat_id, "Support request cancelled. Type /start to begin again.")
                return {"ok": True}
            
            # Regular message processing
            reply = await run_llm(chat_id, user_input)
            send_message(chat_id, reply)
        
        return {"ok": True}
    
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        send_message(chat_id, "Sorry, something went wrong. Please try again.")
        return {"ok": False}

# ==================== STARTUP/SHUTDOWN ====================

@app.on_event("startup")
async def startup_event():
    """Initialize database and test connection on startup"""
    logger.info("🚀 Starting up Gatekeeper Support Platform...")
    
    # Test database connection
    if not test_connection():
        logger.error("❌ Failed to connect to database on startup!")
        raise RuntimeError("Database connection failed")
    
    # Initialize database tables
    if not init_db():
        logger.error("❌ Failed to initialize database on startup!")
        raise RuntimeError("Database initialization failed")
    
    logger.info("✅ Gatekeeper application started successfully")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    logger.info("🛑 Shutting down Gatekeeper Support Platform...")


# ==================== HEALTH CHECKS ====================

@app.get("/health")
async def health_check():
    """
    Health check endpoint.
    
    Returns service status and session statistics.
    """
    from session import sessions
    return {
        "status": "healthy",
        "service": "Gatekeeper Support Platform",
        "version": "2.0.0",
        "active_sessions": len(sessions),
        "conversation_histories": len(conversation_state),
        "timestamp": datetime.utcnow().isoformat()
    }


@app.get("/")
async def root():
    """Root endpoint - API information"""
    return {
        "name": "Gatekeeper Support Platform",
        "version": "2.0.0",
        "status": "running",
        "features": [
            "Admin authentication (Phase 1)",
            "Telegram bot intake (Phase 0)",
            "Chat-based ticket creation",
            "Vision AI image analysis",
            "File uploads support",
            "Semantic search (coming Phase 2)",
            "WhatsApp integration (coming Phase 7)"
        ],
        "endpoints": {
            "health": "/health",
            "auth": "/api/admin/login",
            "telegram": "/telegram/webhook"
        }
    }