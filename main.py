# main.py - ENHANCED with Vision AI for screenshots and videos
from fastapi import FastAPI, Request
import requests
import os
import logging
import base64
import mimetypes
from groq import Groq
from dotenv import load_dotenv

from session import (
    IssueCategory,
    get_or_create_session, 
    clear_session, 
    ValidationError,
    SUPPORTED_SOFTWARE
)
from agent_functions import (
    classify_issue_category, 
    _confirm_and_create_ticket,
    _get_session_data,
    _get_available_options,
    _calculate_completeness
)
from prompt import GATEKEEPER_PROMPT
from http_routes import http_router
from enum import Enum

# ==================== SETUP ====================

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Environment
load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not TELEGRAM_TOKEN:
    raise RuntimeError("Missing TELEGRAM_BOT_TOKEN")
if not GROQ_API_KEY:
    raise RuntimeError("Missing GROQ_API_KEY")

TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
MODEL = "llama-3.1-8b-instant"
VISION_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"
UPLOADS_DIR = "uploads"

# File size limits (in bytes)
MAX_IMAGE_SIZE = 5 * 1024 * 1024  # 5MB for images
MAX_VIDEO_SIZE = 20 * 1024 * 1024  # 20MB for videos

os.makedirs(UPLOADS_DIR, exist_ok=True)

# Groq client
client = Groq(api_key=GROQ_API_KEY)

# FastAPI app
app = FastAPI(title="Gatekeeper Support Intake System")
app.include_router(http_router)

# Conversation history (temporary, per session)
conversation_state: dict[int, list] = {}

# ==================== TELEGRAM HELPERS ====================

def send_message(chat_id: int, text: str) -> bool:
    """Send message to Telegram chat. Returns success status."""
    if not text or not text.strip():
        return False
    
    try:
        resp = requests.post(
            f"{TELEGRAM_API}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=5
        )
        return resp.status_code == 200
    except Exception as e:
        logger.error(f"Telegram send failed: {e}")
        return False


async def download_file(file_id: str, file_name: str, max_size: int = None) -> str | None:
    """Download file from Telegram with optional size limit."""
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
            return None

        url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_path}"
        content = requests.get(url, timeout=10)

        if content.status_code == 200:
            safe_name = os.path.basename(file_name)
            local_path = os.path.join(UPLOADS_DIR, safe_name)
            
            with open(local_path, "wb") as f:
                f.write(content.content)
            
            return local_path
        else:
            return None

    except Exception as e:
        logger.error(f"File download failed: {e}")
        return None


async def analyze_image_with_vision(image_path: str, chat_id: int) -> str | None:
    """
    Analyze image using Groq's vision API to extract observations about the issue.
    Returns analysis text describing what's visible in the image.
    """
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
        
        # Call vision API with proper image_url format
        response = client.chat.completions.create(
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
    Extract structured information from image analysis using LLM with validation constraints.
    Uses same constraints as text extraction to ensure consistency.
    """
    if not analysis_text.strip():
        return
    
    try:
        # Get available options for constrained extraction
        available_options = _get_available_options()
        
        # Use LLM to extract structured data from vision analysis with constraints
        response = client.chat.completions.create(
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
        
        # Parse and apply extracted information with validation
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
                
                # Software extraction - match against SUPPORTED_SOFTWARE
                if not session.software and 'software' in field:
                    value_lower = value.lower()
                    matched = False
                    for keyword, software_name in SUPPORTED_SOFTWARE.items():
                        if keyword in value_lower:
                            try:
                                session.software = software_name
                                logger.info(f"[{chat_id}] Vision: Applied software = {software_name}")
                                matched = True
                            except ValidationError as e:
                                logger.warning(f"[{chat_id}] Vision: Failed to apply software: {e}")
                            break
                    if not matched:
                        # Try direct match
                        try:
                            session.software = value
                            logger.info(f"[{chat_id}] Vision: Applied software = {value}")
                        except ValidationError as e:
                            logger.warning(f"[{chat_id}] Vision: Failed to apply software: {e}")
                
                # Environment extraction - exact match with valid options
                elif not session.environment and 'environment' in field:
                    valid_envs = available_options['environments']
                    for env_option in valid_envs:
                        # Exact match first
                        if value.lower() == env_option.lower():
                            try:
                                session.environment = env_option
                                logger.info(f"[{chat_id}] Vision: Applied environment = {env_option}")
                            except ValidationError as e:
                                logger.warning(f"[{chat_id}] Vision: Failed to apply environment: {e}")
                            break
                        # Partial match as fallback
                        elif value.lower() in env_option.lower() or env_option.lower() in value.lower():
                            try:
                                session.environment = env_option
                                logger.info(f"[{chat_id}] Vision: Applied environment = {env_option}")
                            except ValidationError as e:
                                logger.warning(f"[{chat_id}] Vision: Failed to apply environment: {e}")
                            break
                
                # Impact extraction - keyword mapping with logging
                elif not session.impact and 'impact' in field:
                    impact_set = False
                    if any(kw in value.lower() for kw in ['completely', 'fully', 'blocked', 'unable', 'cannot']):
                        try:
                            session.impact = "Completely blocked"
                            logger.info(f"[{chat_id}] Vision: Applied impact = Completely blocked")
                            impact_set = True
                        except ValidationError as e:
                            logger.warning(f"[{chat_id}] Vision: Failed to apply impact: {e}")
                    
                    elif any(kw in value.lower() for kw in ['partial', 'some']):
                        try:
                            session.impact = "Partially blocked"
                            logger.info(f"[{chat_id}] Vision: Applied impact = Partially blocked")
                            impact_set = True
                        except ValidationError as e:
                            logger.warning(f"[{chat_id}] Vision: Failed to apply impact: {e}")
                    
                    elif any(kw in value.lower() for kw in ['slow', 'sluggish', 'lag', 'usable']):
                        try:
                            session.impact = "Slow but usable"
                            logger.info(f"[{chat_id}] Vision: Applied impact = Slow but usable")
                            impact_set = True
                        except ValidationError as e:
                            logger.warning(f"[{chat_id}] Vision: Failed to apply impact: {e}")
                    
                    if not impact_set:
                        logger.warning(f"[{chat_id}] Vision: Could not map impact: {value}")
                
                # Issue description - from error field
                elif not session.issue_description and 'error' in field and value:
                    # Clean up error message - remove special chars but keep meaningful text
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
    Returns: (success, field_name_saved)
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
    
    # Impact level (check early, before issue description)
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
    
    # Issue description: longer text or contains issue keywords
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
    
    # Name + Company: comma-separated format
    if not session.user_name:
        parts = [p.strip() for p in text.split(",")]
        if len(parts) >= 2 and 2 < len(parts[0]) < 50 and 2 < len(parts[1]) < 100:
            try:
                session.user_name = parts[0]
                session.company_name = parts[1]
                return True, "user_name"
            except ValidationError:
                return False, None
    
    # Just user name (short text, no keywords)
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
    
    # Company name (if we have name but not company)
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
    """Generate a clear summary of collected information with edit options."""
    summary = "📋 Here's what I've collected:\n\n"
    summary += f"1️⃣ Name: {session.user_name}\n"
    summary += f"2️⃣ Company: {session.company_name}\n"
    summary += f"3️⃣ Software: {session.software}\n"
    
    # Environment: extract .value if it's an Enum
    env_display = session.environment.value if session.environment and isinstance(session.environment, Enum) else session.environment
    summary += f"4️⃣ Environment: {env_display}\n"
    
    # Category: extract .value if it's an Enum
    cat_display = session.issue_category.value if session.issue_category and isinstance(session.issue_category, Enum) else session.issue_category
    summary += f"5️⃣ Category: {cat_display}\n"
    
    # Impact: extract .value if it's an Enum
    impact_display = session.impact.value if session.impact and isinstance(session.impact, Enum) else session.impact
    summary += f"6️⃣ Impact: {impact_display}\n"
    
    summary += f"7️⃣ Issue: {session.issue_description}\n"
    
    if session.attachments:
        summary += f"📎 Attachments: {len(session.attachments)} file(s)\n"
    
    summary += "\n✏️ Edit any field: reply 'edit 1-7' (e.g., 'edit 2' to change company)\n"
    summary += "✅ Or reply YES to create the ticket."
    return summary


async def process_pre_confirmation_edit(chat_id: int, edit_request: str, session) -> str:
    """Handle edit request - prompt for new value."""
    # Map field numbers and names to session attributes
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
        return "❌ Invalid field. Use 1-7 or field name (name, company, software, environment, category, impact, issue)"
    
    attr_name, display_name = field_map[edit_request]
    current_value = getattr(session, attr_name, None)
    
    # Store edit state in session
    session.edit_field_mode = True
    session.edit_field_name = attr_name
    session.edit_field_display = display_name
    
    return f"✏️ Editing {display_name}\nCurrent value: {current_value}\n\nWhat should the new value be?"


async def apply_pre_confirmation_edit(chat_id: int, new_value: str, session) -> str:
    """Apply the edited value to the session field."""
    if not hasattr(session, 'edit_field_name') or not session.edit_field_name:
        return "❌ No field in edit mode. Use 'edit 1-7' first."
    
    attr_name = session.edit_field_name
    display_name = session.edit_field_display
    
    try:
        # Validate and apply the new value
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
            # Match category to enum
            category_matched = None
            for cat in IssueCategory:
                if new_value.lower() in cat.value.lower():
                    session.issue_category = cat
                    category_matched = cat.value
                    break
            if not category_matched:
                return f"❌ Invalid category. Valid options: {', '.join([c.value for c in IssueCategory])}"
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
        
        # Clear edit mode
        session.edit_field_mode = False
        session.edit_field_name = None
        session.edit_field_display = None
        
        # Show updated summary
        summary = await generate_summary(session)
        return f"✅ {display_name} updated to: {validated_value}\n\n{summary}"
    
    except ValidationError as e:
        return f"❌ Validation error: {str(e)}\n\nTry again with a valid value or type 'cancel' to skip."
    except Exception as e:
        logger.error(f"[{chat_id}] Edit error: {e}")
        return f"❌ Error updating field: {str(e)}"    """Apply the edited value to the session field."""
    
# ==================== LLM INTEGRATION ====================

async def run_llm(chat_id: int, user_text: str) -> str:
    """
    Run LLM conversation with validation and error handling.
    - LLM guides the conversation and asks for questions
    - System generates summary when all data complete
    - Only create ticket when user confirms summary
    """
    session = get_or_create_session(chat_id)
    history = conversation_state.get(chat_id, [])
    
    # Silent field extraction (non-intrusive)
    await try_extract_field(chat_id, user_text, session)
    
    # Get completeness status
    completeness = _calculate_completeness(session)
    all_collected = completeness['collected'] == completeness['total']
    
    # ========== STEP 1: SUMMARY ALREADY SHOWN ==========
    # If summary was shown before, check for confirmation or edit requests
    if session.summary_shown and not session.ticket_created:
        user_lower = user_text.lower().strip()
        
        # Check if in edit field mode (waiting for new value)
        if hasattr(session, 'edit_field_mode') and session.edit_field_mode:
            return await apply_pre_confirmation_edit(chat_id, user_text, session)
        
        # Check for edit requests (e.g., "edit 2", "edit company")
        if user_lower.startswith('edit '):
            edit_request = user_lower[5:].strip()
            return await process_pre_confirmation_edit(chat_id, edit_request, session)
        
        # Check for confirmation
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
                
                # Clean up session
                clear_session(chat_id)
                conversation_state.pop(chat_id, None)
                
                return reply
            else:
                error_msg = result.get("error", "Unknown error")
                reply = f"Sorry, I couldn't create the ticket: {error_msg}"
                send_message(chat_id, reply)
                return reply
        else:
            # User didn't confirm, show summary again
            summary = await generate_summary(session)
            return summary
    
    # ========== STEP 2: ALL DATA COLLECTED - SHOW SUMMARY ==========
    if all_collected and not session.summary_shown and not session.ticket_created:
        session.summary_shown = True
        summary = await generate_summary(session)
        return summary
    
    # ========== STEP 3: CONTINUE COLLECTING DATA VIA LLM ==========
    # Build system context with session data and available options
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

=== VALID OPTIONS (when needed) ===
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
        resp = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            temperature=0.35,
            max_tokens=250,
            top_p=0.95
        )
        
        reply = (resp.choices[0].message.content or "").strip()
        
        if not reply:
            reply = "Could you tell me a bit more about what you're experiencing?"
        
        # FILTER: Detect and reject LLM-generated summaries
        # If LLM tries to create a summary (bulleted lists, numbered lists, colon-separated values)
        # reject it and ask the next question
        summary_indicators = [
            'issue category:', 'system and environment:', 'impact level:',
            'here\'s', 'summary:', '1.', '2.', '3.',  # Common summary patterns
            'got it', 'thanks', 'understood', 'correct?'  # Common confirmation patterns
        ]
        
        is_summary_attempt = (
            any(indicator in reply.lower() for indicator in summary_indicators) and
            ':' in reply  # Summaries often use field: value format
        )
        
        if is_summary_attempt:
            # LLM tried to create a summary - ignore it and ask next field
            logger.warning(f"[{chat_id}] LLM attempted to generate summary, filtering it out")
            
            # Ask for the first missing field
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
    )[-10:]  # Keep last 10 messages
    
    return reply

async def process_file_with_text(chat_id: int, file_path: str, file_name: str, text: str, session) -> None:
    """Process file attachment along with accompanying text message."""
    file_ext = os.path.splitext(file_name)[1].lower()
    
    # Analyze image with vision if it's an image
    if file_ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']:
        analysis = await analyze_image_with_vision(file_path, chat_id)
        if analysis:
            await extract_info_from_image_analysis(chat_id, analysis, session)
    
    # Also extract from the text if provided
    if text and text.strip():
        await try_extract_field(chat_id, text, session)

# ==================== TICKET EDITING ====================

async def show_ticket_for_editing(chat_id: int, ticket_id: str) -> tuple[bool, str]:
    """Load and display a ticket for editing."""
    from ticket import load_ticket_by_id
    
    ticket_data = load_ticket_by_id(ticket_id)
    if not ticket_data:
        return False, f"❌ Ticket {ticket_id} not found. Please check the ticket ID."
    
    # Show ticket data with edit options
    display = f"""📋 Ticket {ticket_id}
    
👤 Name: {ticket_data.get('user_name')}
🏢 Company: {ticket_data.get('company_name')}
⚙️  Software: {ticket_data.get('software')}
🌍 Environment: {ticket_data.get('environment')}
📌 Category: {ticket_data.get('issue_category')}
⚠️  Impact: {ticket_data.get('impact')}
📄 Issue: {ticket_data.get('issue_description')}

Reply with field name and new value to edit:
- name: <new name>
- company: <new company>
- software: <software name>
- environment: <Production/Test/Local>
- category: <category name>
- impact: <impact level>
- issue: <issue description>

Or reply DONE when finished editing."""
    
    # Store ticket data in session for editing
    session = get_or_create_session(chat_id)
    session.edit_mode = True
    session.edit_ticket_id = ticket_id
    session.edit_ticket_data = ticket_data
    
    return True, display


async def process_ticket_edit(chat_id: int, user_input: str, session) -> str:
    """Process an edit command for a ticket."""
    from ticket import update_ticket
    
    user_input = user_input.strip()
    
    # Check if editing is done
    if user_input.lower() in ['done', 'finish', 'save']:
        if hasattr(session, 'edit_mode') and session.edit_mode:
            session.edit_mode = False
            session.edit_ticket_id = None
            session.edit_ticket_data = None
            ticket_id = session.edit_ticket_id if hasattr(session, 'edit_ticket_id') else "Unknown"
            reply = f"✅ Ticket updated successfully!"
            return reply
        else:
            return "No ticket in edit mode."
    
    # Parse edit command: "field: value"
    if ':' not in user_input:
        return "Please use format: field: value (e.g., 'software: Teamcenter')"
    
    field_name, field_value = user_input.split(':', 1)
    field_name = field_name.strip().lower()
    field_value = field_value.strip()
    
    if not field_value:
        return f"Field value cannot be empty."
    
    # Map field names to ticket data keys
    field_mapping = {
        'name': 'user_name',
        'company': 'company_name',
        'software': 'software',
        'environment': 'environment',
        'category': 'issue_category',
        'impact': 'impact',
        'issue': 'issue_description',
    }
    
    if field_name not in field_mapping:
        return f"❌ Unknown field: {field_name}. Available fields: {', '.join(field_mapping.keys())}"
    
    data_key = field_mapping[field_name]
    
    # Validate the field value based on field type
    try:
        # Create a temporary session to validate
        temp_session = get_or_create_session(chat_id)
        
        if field_name == 'name':
            temp_session.user_name = field_value
            validated_value = temp_session.user_name
        elif field_name == 'company':
            temp_session.company_name = field_value
            validated_value = temp_session.company_name
        elif field_name == 'software':
            temp_session.software = field_value
            validated_value = temp_session.software
        elif field_name == 'environment':
            temp_session.environment = field_value
            validated_value = temp_session.environment.value
        elif field_name == 'category':
            category_matched = None
            for cat in IssueCategory:
                if field_value.lower() in cat.value.lower():
                    category_matched = cat.value
                    break
            if not category_matched:
                return f"❌ Invalid category: {field_value}. Valid: {', '.join([c.value for c in IssueCategory])}"
            validated_value = category_matched
        elif field_name == 'impact':
            temp_session.impact = field_value
            validated_value = temp_session.impact.value
        elif field_name == 'issue':
            temp_session.issue_description = field_value
            validated_value = temp_session.issue_description
        
    except ValidationError as e:
        return f"❌ Validation error: {str(e)}"
    
    # Update the ticket
    ticket_id = session.edit_ticket_id
    update_data = {data_key: validated_value}
    
    if update_ticket(ticket_id, update_data):
        # Update the local cache
        session.edit_ticket_data[data_key] = validated_value
        
        # Show updated ticket state
        summary = f"""✏️ Updated {field_name}: {validated_value}

Current ticket state:
👤 Name: {session.edit_ticket_data.get('user_name')}
🏢 Company: {session.edit_ticket_data.get('company_name')}
⚙️ Software: {session.edit_ticket_data.get('software')}
🌍 Environment: {session.edit_ticket_data.get('environment')}
📌 Category: {session.edit_ticket_data.get('issue_category')}
⚠️ Impact: {session.edit_ticket_data.get('impact')}
📄 Issue: {session.edit_ticket_data.get('issue_description')}

Edit another field or reply DONE."""
        return summary
    else:
        return f"❌ Failed to update ticket {ticket_id}. Please try again."

# ==================== WEBHOOK ====================

@app.post("/telegram/webhook")
async def telegram_webhook(req: Request):
    """Handle incoming Telegram webhook."""
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
        
        # Get text if present (works with or without attachments)
        text = msg.get("text", "").strip() if "text" in msg else ""
        caption = msg.get("caption", "").strip() if "caption" in msg else ""
        user_input = text or caption
        
        # File upload (document) - process silently, no custom message
        if "document" in msg:
            file_name = msg["document"].get("file_name", "document")
            path = await download_file(msg["document"]["file_id"], file_name, max_size=MAX_IMAGE_SIZE)
            if path:
                session.attachments.append(path)
                # Process file silently - extract data without custom response
                await process_file_with_text(chat_id, path, file_name, user_input, session)
                
                # If there's accompanying text, let run_llm handle the response
                if user_input:
                    reply = await run_llm(chat_id, user_input)
                    send_message(chat_id, reply)
                # If no text, send acknowledgment only
                else:
                    send_message(chat_id, "📎 Got the file. Please continue.")
            else:
                send_message(chat_id, "❌ Failed to download file. File may be too large (max 5MB).")
            return {"ok": True}
        
        # Photo upload - process silently, no custom message
        if "photo" in msg:
            photo = msg["photo"][-1]
            path = await download_file(photo["file_id"], f"screenshot_{chat_id}_{len(session.attachments)}.jpg", max_size=MAX_IMAGE_SIZE)
            if path:
                session.attachments.append(path)
                # Process photo silently - extract data without custom response
                await process_file_with_text(chat_id, path, f"screenshot.jpg", user_input, session)
                
                # If there's accompanying text, let run_llm handle the response
                if user_input:
                    reply = await run_llm(chat_id, user_input)
                    send_message(chat_id, reply)
                # If no caption, send acknowledgment only
                else:
                    send_message(chat_id, "📸 Got the screenshot. Please continue.")
            else:
                send_message(chat_id, "❌ Failed to download screenshot. File may be too large (max 5MB).")
            return {"ok": True}
        
        # Video upload - process silently, no custom message
        if "video" in msg:
            video = msg["video"]
            video_name = f"video_{chat_id}_{len(session.attachments)}.mp4"
            path = await download_file(video["file_id"], video_name, max_size=MAX_VIDEO_SIZE)
            if path:
                session.attachments.append(path)
                # Process video silently - extract data without custom response
                if user_input:
                    await try_extract_field(chat_id, user_input, session)
                
                # If there's accompanying text, let run_llm handle the response
                if user_input:
                    reply = await run_llm(chat_id, user_input)
                    send_message(chat_id, reply)
                # If no caption, send acknowledgment only
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
                # Extract ticket ID
                ticket_id = user_input[6:].strip().upper()
                if not ticket_id:
                    send_message(chat_id, "Usage: /edit <ticket_id>")
                    return {"ok": True}
                
                success, message = await show_ticket_for_editing(chat_id, ticket_id)
                send_message(chat_id, message)
                return {"ok": True}
            
            if user_input.lower() == "/cancel":
                clear_session(chat_id)
                conversation_state.pop(chat_id, None)
                session.edit_mode = False if hasattr(session, 'edit_mode') else False
                send_message(chat_id, "Support request cancelled. Type /start to begin again.")
                return {"ok": True}
            
            # Check if in saved ticket edit mode (/edit <ticket_id>)
            if hasattr(session, 'edit_mode') and session.edit_mode:
                reply = await process_ticket_edit(chat_id, user_input, session)
                send_message(chat_id, reply)
                return {"ok": True}
            
            # Check if in pre-confirmation edit mode (new ticket edit before confirmation)
            if hasattr(session, 'edit_field_mode') and session.edit_field_mode:
                reply = await apply_pre_confirmation_edit(chat_id, user_input, session)
                send_message(chat_id, reply)
                return {"ok": True}
            
            # Regular message processing - uses generate_summary() template automatically
            reply = await run_llm(chat_id, user_input)
            send_message(chat_id, reply)
        
        return {"ok": True}
    
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        send_message(chat_id, "Sorry, something went wrong. Please try again.")
        return {"ok": False}

# ==================== HEALTH CHECK ====================

@app.get("/health")
async def health():
    """Health check endpoint."""
    from session import sessions
    return {
        "status": "ok",
        "active_sessions": len(sessions),
        "conversation_histories": len(conversation_state)
    }

@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": "Gatekeeper Support Intake System",
        "version": "2.0",
        "status": "running",
        "features": ["Chat-based intake", "Vision AI analysis", "File uploads"]
    }