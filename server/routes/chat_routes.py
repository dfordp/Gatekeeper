# server/routes/chat_routes.py
"""
Chat Routes - Telegram webhook handler with cache decorators

Endpoints:
- POST /api/chat/webhook - Telegram message webhook
- GET /api/chat/session/{session_id} - Get chat session details
- POST /api/chat/search - Search for solutions (non-webhook)
- POST /api/chat/feedback - Record search feedback for adaptive thresholds
"""

import logging
import json
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Request, HTTPException, Depends
from utils.datetime_utils import to_iso_date
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from core.database import (
    get_db, ChatSession, User, Company, Ticket, ChatAttachment, TicketEvent
)
from core.config import TELEGRAM_BOT_TOKEN, TELEGRAM_API
from middleware.cache_decorator import cache_endpoint, invalidate_on_mutation
from services.chat_ticket_service import ChatTicketService
from services.chat_search_service import ChatSearchService
from utils.exceptions import ValidationError
from middleware.auth_middleware import get_current_admin
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"])

# Initialize services
chat_ticket_service = ChatTicketService()
chat_search_service = ChatSearchService()


@router.post("/webhook")
@invalidate_on_mutation(tags=["chat:sessions", "ticket:list"])
async def handle_telegram_webhook(request: Request, db: Session = Depends(get_db)):
    """
    Handle incoming Telegram messages.
    """
    try:
        body = await request.json()
        logger.info(f"Received webhook from Telegram user: {body.get('message', {}).get('from', {}).get('id')}")
        
        
        # Extract Telegram update
        message = body.get("message", {})
        chat_id = message.get("chat", {}).get("id")
        telegram_user_id = message.get("from", {}).get("id")
        text = message.get("text", "").strip()
        photo = message.get("photo")
        document = message.get("document")
        caption = message.get("caption", "").strip()
        
        logger.info(f"Message content: text={bool(text)}, photo={bool(photo)}, document={bool(document)}, caption={bool(caption)}")
        logger.info(f"Full message object: {json.dumps(message, default=str)}")
        
        if not chat_id or not telegram_user_id:
            logger.warning("Missing chat_id or telegram_user_id in webhook")
            return {"status": "ok"}
        
        # Find chat session by telegram_chat_id
        chat_session = db.query(ChatSession).filter(
            ChatSession.telegram_chat_id == str(chat_id)
        ).first()
        
        if not chat_session:
            logger.warning(f"ChatSession not found for telegram_chat_id={chat_id}")
            await _send_telegram_message(
                chat_id=chat_id,
                text="🤖 Welcome to Gatekeeper Chat!\n\n"
                     "To get started, please initialize your chat session from the web interface.\n"
                     "You'll need to be logged in with your credentials."
            )
            return {"status": "ok"}
        
        # Verify session is still active
        if not chat_session.is_active:
            logger.warning(f"Chat session not active for user {chat_session.user_id}")
            await _send_telegram_message(
                chat_id=chat_id,
                text="⚠️ Your chat session has been deactivated.\n"
                     "Please contact your administrator."
            )
            return {"status": "ok"}
        
        # Update last message time
        chat_session.last_message_at = datetime.utcnow()
                
        response = None
        
        # Handle text messages
        if text:
            logger.info(f"Handling text message: {text[:50]}...")
            response = await _handle_text_message(
                text=text,
                chat_session=chat_session,
                db=db
            )
        
        # Handle photo messages (with or without caption)
        elif photo:
            logger.info(f"Handling photo message with {len(photo)} photo(s), caption={bool(caption)}")
            response = await _handle_photo_message(
                photo=photo,
                chat_session=chat_session,
                message=message,
                db=db
            )
        
        # Handle document messages (files, screenshots, etc. with optional caption)
        elif document:
            logger.info(f"Handling document message: {document.get('file_name')}, caption={bool(caption)}")
            response = await _handle_document_message(
                document=document,
                chat_session=chat_session,
                message=message,
                db=db
            )
        
        # Handle caption-only (document with caption but no text field)
        elif caption:
            logger.info(f"Handling caption-only message ({len(caption)} chars): {caption[:50]}...")
            # Treat caption as text message
            response = await _handle_text_message(
                text=caption,
                chat_session=chat_session,
                db=db
            )
        
        else:
            logger.warning("Message has no text, photo, document, or caption")
        
        if response:
            logger.info(f"Sending response: {response[:100]}...")
            await _send_telegram_message(chat_id=chat_id, text=response)
        else:
            logger.warning("No response generated from message handler")
        
        db.commit()
        return {"status": "ok"}
    
    except Exception as e:
        logger.error(f"Error handling webhook: {e}", exc_info=True)
        return {"status": "ok"}


async def _handle_text_message(
    text: str,
    chat_session: ChatSession,
    db: Session
) -> Optional[str]:
    """Handle text messages with stateful confirmation flow"""
    
    try:
        # Initialize session state
        if not chat_session.session_state:
            chat_session.session_state = {}
        
        state = chat_session.session_state
        waiting_for_confirmation = state.get("waiting_for_confirmation", False)
        pending_issue = state.get("pending_issue")
        pending_analysis = state.get("pending_analysis")
        
        logger.info(f"State check: waiting={waiting_for_confirmation}, issue={'✓' if pending_issue else '✗'}, analysis={'✓' if pending_analysis else '✗'}")
        
        # ============================================================
        # STATE: User is confirming ticket creation
        # ============================================================
        if waiting_for_confirmation and pending_issue and pending_analysis:
            logger.info(f"User confirmation state detected. User input: {text}")
            response_lower = text.lower().strip()
            
            if response_lower in ["yes", "y", "confirm", "create", "ok"]:
                # User confirmed - create ticket
                try:
                    logger.info(f"Creating ticket with category: {pending_analysis.get('inferred_category')}")
                    ticket_result = chat_ticket_service.create_ticket_from_chat(
                        chat_session_id=chat_session.id,
                        issue_description=pending_issue,
                        inferred_category=pending_analysis.get("inferred_category")
                    )
                    
                    # Clear pending state
                    chat_session.session_state["waiting_for_confirmation"] = False
                    chat_session.session_state["pending_issue"] = None
                    chat_session.session_state["pending_analysis"] = None
                    flag_modified(chat_session, "session_state")
                    db.commit()
                    
                    logger.info(f"✓ Ticket created successfully: {ticket_result.get('ticket_no')}")
                    return (
                        f"✅ Ticket created: {ticket_result.get('ticket_no')}\n"
                        f"Category: {ticket_result.get('inferred_category')}\n\n"
                        f"The issue is being analyzed. You'll receive updates as we work on it."
                    )
                
                except Exception as e:
                    logger.error(f"Error creating ticket: {e}", exc_info=True)
                    chat_session.session_state["waiting_for_confirmation"] = False
                    flag_modified(chat_session, "session_state")
                    db.commit()
                    return f"❌ Failed to create ticket: {str(e)}"
            
            elif response_lower in ["no", "n", "cancel", "skip"]:
                # User declined
                logger.info("User declined ticket creation")
                chat_session.session_state["waiting_for_confirmation"] = False
                chat_session.session_state["pending_issue"] = None
                chat_session.session_state["pending_analysis"] = None
                flag_modified(chat_session, "session_state")
                db.commit()
                return "✓ Cancelled. Send another message to get started."
            
            else:
                logger.info(f"Invalid confirmation response: {text}")
                return (
                    "Please confirm by replying:\n"
                    "✅ Yes / Confirm / Create\n"
                    "❌ No / Cancel / Skip"
                )
        
        # ============================================================
        # NORMAL STATE: User is sending a message
        # ============================================================
        
        # Special commands
        if text.lower() == "/help":
            return _get_help_message()
        
        elif text.lower() == "/status":
            return _get_session_status(chat_session)
        
        elif text.lower().startswith("/search"):
            query = text[7:].strip()
            if not query:
                return "Please provide a search query: /search <your issue>"
            
            results = chat_search_service.search_for_solutions(
                query=query,
                company_id=chat_session.company_id,
                limit=3
            )
            
            return _format_search_results(results)
        
        # Regular message handling
        if len(text) >= 20:
            # Long message - analyze and ask for confirmation
            logger.info(f"Long message ({len(text)} chars): analyzing...")
            try:
                analysis = chat_ticket_service.analyze_issue_for_chat(
                    chat_session_id=chat_session.id,
                    issue_description=text
                )
                
                logger.info(f"Analysis complete: category={analysis.get('inferred_category')}, solutions={len(analysis.get('similar_solutions', []))}")
                
                # Store for confirmation step
                chat_session.session_state["waiting_for_confirmation"] = True
                chat_session.session_state["pending_issue"] = text
                chat_session.session_state["pending_analysis"] = analysis
                flag_modified(chat_session, "session_state")
                db.commit()
                
                # Build response with analysis and solutions
                inferred_category = analysis.get("inferred_category", "other")
                similar_solutions = analysis.get("similar_solutions", [])
                adaptive_threshold = analysis.get("adaptive_threshold")
                
                response = (
                    f"📋 Issue: {text[:100]}...\n\n"
                    f"🏷️ Category: {inferred_category}\n"
                    f"📊 Confidence threshold: {adaptive_threshold:.0%}\n\n"
                )
                
                # Show similar solutions if found
                if similar_solutions:
                    response += "📚 Similar solutions found:\n"
                    for i, sol in enumerate(similar_solutions, 1):
                        similarity_pct = int(sol.get("similarity_score", 0) * 100)
                        response += (
                            f"\n{i}. {sol.get('ticket_no')} - {sol.get('subject')}\n"
                            f"   Category: {sol.get('category')} ({similarity_pct}% match)\n"
                        )
                    response += "\n"
                else:
                    response += "🔍 No existing solutions found.\n\n"
                
                response += "Should I create a ticket for this issue?\nReply: yes or no"
                
                logger.info(f"Sending analysis response to user")
                return response
            
            except ValidationError as e:
                logger.warning(f"Validation error: {e}")
                return f"❌ {str(e)}"
            except Exception as e:
                logger.error(f"Error analyzing issue: {e}", exc_info=True)
                return "❌ Error analyzing issue. Please try again."
        
        else:
            # Short message - search only
            logger.info(f"Short message ({len(text)} chars): search only")
            results = chat_search_service.search_for_solutions(
                query=text,
                company_id=chat_session.company_id,
                limit=3
            )
            
            if results:
                response = "📚 Similar solutions found:\n"
                response += _format_search_results(results)
                response += "\n\nSend a longer message (20+ chars) to create a new ticket."
                return response
            else:
                return "No similar solutions found. Send a longer message to create a ticket."
    
    except Exception as e:
        logger.error(f"Error handling text message: {e}")
        return "❌ Error processing message. Please try again."


async def _handle_photo_message(
    photo: list,
    chat_session: ChatSession,
    message: Dict,
    db: Session
) -> Optional[str]:
    """Handle photo messages from Telegram with stateful confirmation"""
    
    try:
        # Get largest photo
        largest_photo = max(photo, key=lambda x: x.get("file_size", 0))
        file_id = largest_photo.get("file_id")
        
        if not file_id:
            return "❌ Could not process photo"
        
        # Download photo from Telegram
        file_path = await _download_telegram_file(file_id)
        
        if not file_path:
            return "❌ Failed to download photo"
        
        # Store in ChatAttachment with auto-expiry
        expires_at = datetime.utcnow() + timedelta(hours=24)
        
        chat_attachment = ChatAttachment(
            chat_session_id=chat_session.id,
            local_file_path=file_path,
            file_name=f"telegram_{file_id}.jpg",
            mime_type="image/jpeg",
            created_at=datetime.utcnow(),
            expires_at=expires_at
        )
        db.add(chat_attachment)
        db.commit()
        
        logger.info(f"Photo stored: {file_path}")
        
        # Get caption if provided
        caption = message.get("caption", "").strip()
        
        # If caption provided and long enough, analyze and ask for confirmation
        if caption and len(caption) >= 10:
            logger.info(f"Photo with caption ({len(caption)} chars): analyzing...")
            try:
                issue_description = f"{caption}\n[Photo attached]"
                
                analysis = chat_ticket_service.analyze_issue_for_chat(
                    chat_session_id=chat_session.id,
                    issue_description=issue_description,
                    image_path=file_path  # Pass the image path
                )
                
                logger.info(f"Analysis complete: category={analysis.get('inferred_category')}, solutions={len(analysis.get('similar_solutions', []))}")
                
                # Store for confirmation step
                chat_session.session_state = chat_session.session_state or {}
                chat_session.session_state["waiting_for_confirmation"] = True
                chat_session.session_state["pending_issue"] = issue_description
                chat_session.session_state["pending_analysis"] = analysis
                chat_session.session_state["pending_attachment_id"] = str(chat_attachment.id)
                flag_modified(chat_session, "session_state")
                db.commit()
                
                # Build response with analysis and solutions
                inferred_category = analysis.get("inferred_category", "other")
                similar_solutions = analysis.get("similar_solutions", [])
                adaptive_threshold = analysis.get("adaptive_threshold")
                
                response = (
                    f"📷 Photo received with caption: {caption[:100]}...\n\n"
                    f"🏷️ Category: {inferred_category}\n"
                    f"📊 Confidence threshold: {adaptive_threshold:.0%}\n\n"
                )
                
                # Show similar solutions if found
                if similar_solutions:
                    response += "📚 Similar solutions found:\n"
                    for i, sol in enumerate(similar_solutions, 1):
                        similarity_pct = int(sol.get("similarity_score", 0) * 100)
                        response += (
                            f"\n{i}. {sol.get('ticket_no')} - {sol.get('subject')}\n"
                            f"   Category: {sol.get('category')} ({similarity_pct}% match)\n"
                        )
                    response += "\n"
                else:
                    response += "🔍 No existing solutions found.\n\n"
                
                response += "Should I create a ticket for this issue?\nReply: yes or no"
                
                logger.info(f"Sending analysis response to user")
                return response
            
            except Exception as e:
                logger.error(f"Error analyzing photo with caption: {e}", exc_info=True)
                return "❌ Error analyzing issue. Please try again."
        
        else:
            # Photo without caption or short caption
            return "✓ Photo received. Please describe your issue and I'll create a ticket.\n(Send a message with 20+ characters)"
    
    except Exception as e:
        logger.error(f"Error handling photo message: {e}")
        return "❌ Error processing photo. Please try again."
    
async def _handle_document_message(
    document: dict,
    chat_session: ChatSession,
    message: Dict,
    db: Session
) -> Optional[str]:
    """Handle document messages from Telegram with stateful confirmation"""
    
    try:
        file_id = document.get("file_id")
        file_name = document.get("file_name", "document")
        
        if not file_id:
            return "❌ Could not process document"
        
        # Download document from Telegram
        file_path = await _download_telegram_file(file_id)
        
        if not file_path:
            return "❌ Failed to download document"
        
        # Store in ChatAttachment with auto-expiry
        expires_at = datetime.utcnow() + timedelta(hours=24)
        
        chat_attachment = ChatAttachment(
            chat_session_id=chat_session.id,
            local_file_path=file_path,
            file_name=file_name,
            mime_type=document.get("mime_type", "application/octet-stream"),
            created_at=datetime.utcnow(),
            expires_at=expires_at
        )
        db.add(chat_attachment)
        db.commit()
        
        logger.info(f"Document stored: {file_path}")
        
        # Get caption if provided
        caption = message.get("caption", "").strip()
        
        # If caption provided and long enough, analyze and ask for confirmation
        if caption and len(caption) >= 10:
            logger.info(f"Document with caption ({len(caption)} chars): analyzing...")
            try:
                issue_description = f"{caption}\n[Document: {file_name}]"
                
                analysis = chat_ticket_service.analyze_issue_for_chat(
                    chat_session_id=chat_session.id,
                    issue_description=issue_description,
                    image_path=file_path
                )
                
                logger.info(f"Analysis complete: category={analysis.get('inferred_category')}, solutions={len(analysis.get('similar_solutions', []))}")
                
                # Store for confirmation step
                chat_session.session_state = chat_session.session_state or {}
                chat_session.session_state["waiting_for_confirmation"] = True
                chat_session.session_state["pending_issue"] = issue_description
                chat_session.session_state["pending_analysis"] = analysis
                chat_session.session_state["pending_attachment_id"] = str(chat_attachment.id)
                flag_modified(chat_session, "session_state")
                db.commit()
                
                # Build response with analysis and solutions
                inferred_category = analysis.get("inferred_category", "other")
                similar_solutions = analysis.get("similar_solutions", [])
                adaptive_threshold = analysis.get("adaptive_threshold")
                
                response = (
                    f"📄 Document received: {file_name}\n"
                    f"Caption: {caption[:100]}...\n\n"
                    f"🏷️ Category: {inferred_category}\n"
                    f"📊 Confidence threshold: {adaptive_threshold:.0%}\n\n"
                )
                
                # Show similar solutions if found
                if similar_solutions:
                    response += "📚 Similar solutions found:\n"
                    for i, sol in enumerate(similar_solutions, 1):
                        similarity_pct = int(sol.get("similarity_score", 0) * 100)
                        response += (
                            f"\n{i}. {sol.get('ticket_no')} - {sol.get('subject')}\n"
                            f"   Category: {sol.get('category')} ({similarity_pct}% match)\n"
                        )
                    response += "\n"
                else:
                    response += "🔍 No existing solutions found.\n\n"
                
                response += "Should I create a ticket for this issue?\nReply: yes or no"
                
                logger.info(f"Sending analysis response to user")
                return response
            
            except Exception as e:
                logger.error(f"Error analyzing document with caption: {e}", exc_info=True)
                return "❌ Error analyzing issue. Please try again."
        
        else:
            # Document without caption or short caption
            return "✓ Document received. Please describe your issue and I'll create a ticket.\n(Send a message with 20+ characters)"
    
    except Exception as e:
        logger.error(f"Error handling document message: {e}")
        return "❌ Error processing document. Please try again."


@router.get("/session/{session_id}")
@cache_endpoint(ttl=300, tag="chat:session", key_params=["session_id"])
async def get_chat_session(
    session_id: str,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Get chat session details"""
    
    try:
        chat_session = db.query(ChatSession).filter(
            ChatSession.id == UUID(session_id)
        ).first()
        
        if not chat_session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        return {
            "id": str(chat_session.id),
            "user_id": str(chat_session.user_id),
            "company_id": str(chat_session.company_id),
            "telegram_chat_id": chat_session.telegram_chat_id,
            "is_active": chat_session.is_active,
            "session_state": chat_session.session_state,
            "created_at": to_iso_date(chat_session.created_at),
            "last_message_at": to_iso_date(chat_session.last_message_at),
            "closed_at": to_iso_date(chat_session.closed_at) if chat_session.closed_at else None
        }
    
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid session ID")


@router.post("/search")
@cache_endpoint(ttl=60, tag="chat:search", key_params=["company_id"])
async def search_solutions(
    query: str,
    company_id: str,
    limit: int = 5,
    min_similarity: float = 0.55,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Search for solutions (non-webhook endpoint for testing).
    
    Used for direct API calls instead of via Telegram.
    """
    
    try:
        company = db.query(Company).filter(Company.id == UUID(company_id)).first()
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")
        
        results = chat_search_service.search_for_solutions(
            query=query,
            company_id=UUID(company_id),
            limit=limit,
            min_similarity=min_similarity
        )
        
        return {
            "query": query,
            "results_count": len(results),
            "results": results
        }
    
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid company ID")


@router.post("/feedback")
@invalidate_on_mutation(tags=["chat:search", "adaptive:thresholds"])
async def record_search_feedback(
    ticket_id: str,
    similarity_score: float,
    was_helpful: bool,
    rating: Optional[int] = None,
    db: Session = Depends(get_db)
) -> Dict[str, str]:
    """
    Record user feedback about search results.
    
    Used by AdaptiveThresholdService to learn what thresholds work best.
    This data improves category classification over time.
    """
    
    try:
        ticket = db.query(Ticket).filter(Ticket.id == UUID(ticket_id)).first()
        if not ticket:
            raise HTTPException(status_code=404, detail="Ticket not found")
        
        # Create feedback event
        event = TicketEvent(
            ticket_id=UUID(ticket_id),
            event_type="search_result_helpful" if was_helpful else "search_result_not_helpful",
            actor_user_id=ticket.raised_by_user_id,
            payload={
                "similarity_score": similarity_score,
                "rating": rating,
                "timestamp": to_iso_date(datetime.utcnow())
            }
        )
        db.add(event)
        db.commit()
        
        logger.info(
            f"Recorded feedback: ticket={ticket.ticket_no}, "
            f"helpful={was_helpful}, rating={rating}, similarity={similarity_score:.3f}"
        )
        
        return {"status": "recorded", "ticket_no": ticket.ticket_no}
    
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid ticket ID")


# ==================== HELPER FUNCTIONS ====================

def _get_help_message() -> str:
    """Get help message"""
    return """🤖 Gatekeeper Chat Assistant

Commands:
/help - Show this message
/status - View your chat session status
/search <query> - Search for similar issues
/ticket <description> - Create a new ticket

Or just send a message:
• Short message (< 20 chars) → Search for similar issues
• Long message (≥ 20 chars) → Create a ticket + search

📸 You can also share screenshots - add a description for better results!
"""


def _get_session_status(chat_session: ChatSession) -> str:
    """Get session status message"""
    
    status = "✓ Active" if chat_session.is_active else "⚠️ Inactive"
    
    return f"""📊 Chat Session Status

User: {chat_session.user_id}
Company: {chat_session.company_id}
Status: {status}
Created: {chat_session.created_at.strftime('%Y-%m-%d %H:%M:%S')}
Last message: {chat_session.last_message_at.strftime('%Y-%m-%d %H:%M:%S')}

Session state: {json.dumps(chat_session.session_state or {}, indent=2)}
"""


def _format_search_results(results: list, limit: int = 3) -> str:
    """Format search results for Telegram"""
    
    if not results:
        return "No results found."
    
    response = ""
    for i, result in enumerate(results[:limit], 1):
        response += f"\n{i}. {result.get('ticket_no')} - {result.get('solution_title')}\n"
        response += f"   Category: {result.get('category')}\n"
        response += f"   Match: {result.get('similarity_score', 0):.0%}\n"
        
        if result.get('rca_available'):
            response += f"   ✓ Has RCA\n"
    
    return response


async def _send_telegram_message(chat_id: int, text: str) -> bool:
    """Send message back to Telegram"""
    
    try:
        if not TELEGRAM_API:
            logger.warning("TELEGRAM_API not configured")
            return False
        
        import httpx
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{TELEGRAM_API}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": text,

                },
                timeout=10.0
            )
            
            if response.status_code != 200:
                logger.error(f"Failed to send Telegram message: {response.text}")
                return False
            
            return True
    
    except Exception as e:
        logger.error(f"Error sending Telegram message: {e}")
        return False


async def _download_telegram_file(file_id: str) -> Optional[str]:
    """Download file from Telegram"""
    
    try:
        if not TELEGRAM_API or not TELEGRAM_BOT_TOKEN:
            return None
        
        import httpx
        import os
        
        # Get file info
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{TELEGRAM_API}/getFile",
                params={"file_id": file_id},
                timeout=10.0
            )
            
            if response.status_code != 200:
                logger.error(f"Failed to get file info: {response.text}")
                return None
            
            file_info = response.json().get("result", {})
            file_path = file_info.get("file_path")
            
            if not file_path:
                return None
            
            # Download file
            file_url = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}"
            
            file_response = await client.get(file_url, timeout=10.0)
            if file_response.status_code != 200:
                logger.error(f"Failed to download file: {file_response.text}")
                return None
            
            # Save locally
            local_path = f"uploads/chat/{file_id}.jpg"
            os.makedirs("uploads/chat", exist_ok=True)
            
            with open(local_path, "wb") as f:
                f.write(file_response.content)
            
            logger.info(f"Downloaded file to {local_path}")
            return local_path
    
    except Exception as e:
        logger.error(f"Error downloading Telegram file: {e}")
        return None
    
@router.post("/init")
@invalidate_on_mutation(tags=["chat:sessions"])
async def init_chat_session(
    user_id: str,
    telegram_chat_id: str,
    admin_payload: dict = Depends(get_current_admin),  # Only admins can create sessions
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Create a chat session for a user.
    
    Only admins can initialize chat sessions for users.
    Called from admin UI to grant user access to Telegram chat.
    
    Requires: Admin JWT token
    
    Args:
        user_id: UUID of the user to enable chat for
        telegram_chat_id: The Telegram chat ID to link
        admin_payload: Authenticated admin info from JWT
        
    Returns:
        Session details with success message
    """
    try:
        # Get the user
        user = db.query(User).filter(User.id == UUID(user_id)).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Check if session already exists for this user
        existing = db.query(ChatSession).filter(
            ChatSession.user_id == UUID(user_id)
        ).first()
        
        if existing:
            # Session exists - update telegram_chat_id if different
            old_telegram_id = existing.telegram_chat_id
            existing.telegram_chat_id = str(telegram_chat_id)
            db.commit()
            
            logger.info(
                f"✓ Chat session updated by admin: user={user.email}, "
                f"telegram={old_telegram_id} → {telegram_chat_id}"
            )
            
            return {
                "status": "updated",
                "session_id": str(existing.id),
                "user": user.email,
                "company": user.company.name,
                "telegram_chat_id": str(existing.telegram_chat_id),
                "message": f"Chat session updated for {user.email}"
            }
        
        # Create new session for this user
        chat_session = ChatSession(
            user_id=UUID(user_id),
            company_id=user.company_id,
            telegram_chat_id=str(telegram_chat_id),
            session_state={"initialized_by_admin": admin_payload.get("id"), "initialized_at": to_iso_date(datetime.utcnow())}
        )
        
        db.add(chat_session)
        db.commit()
        
        logger.info(
            f"✓ Chat session created by admin: user={user.email}, "
            f"company={user.company.name}, telegram={telegram_chat_id}, "
            f"admin={admin_payload.get('email')}"
        )
        
        return {
            "status": "created",
            "session_id": str(chat_session.id),
            "user": user.email,
            "company": user.company.name,
            "telegram_chat_id": str(telegram_chat_id),
            "message": f"✓ Chat session created for {user.email}. They can now use Telegram."
        }
    
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid ID format: {str(e)}")
    except Exception as e:
        logger.error(f"Error creating chat session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions")
@cache_endpoint(ttl=300, tag="chat:sessions")
async def list_chat_sessions(
    admin_payload: dict = Depends(get_current_admin),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    List all chat sessions (admin only).
    
    Used to manage user chat access from admin dashboard.
    """
    try:
        sessions = db.query(ChatSession).all()
        
        return {
            "total": len(sessions),
            "sessions": [
                {
                    "session_id": str(s.id),
                    "user": s.user.email,
                    "company": s.user.company.name,
                    "telegram_chat_id": s.telegram_chat_id,
                    "is_active": s.is_active,
                    "created_at": to_iso_date(s.created_at),
                    "last_message_at": to_iso_date(s.last_message_at)
                }
                for s in sessions
            ]
        }
    except Exception as e:
        logger.error(f"Error listing sessions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/sessions/{session_id}")
@invalidate_on_mutation(tags=["chat:sessions"])
async def delete_chat_session(
    session_id: str,
    admin_payload: dict = Depends(get_current_admin),
    db: Session = Depends(get_db)
) -> Dict[str, str]:
    """
    Delete a chat session (admin only).
    
    Permanently removes the chat session and all associated attachments.
    """
    try:
        session = db.query(ChatSession).filter(
            ChatSession.id == UUID(session_id)
        ).first()
        
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        user_email = session.user.email
        
        # Delete associated attachments first
        attachments = db.query(ChatAttachment).filter(
            ChatAttachment.chat_session_id == UUID(session_id)
        ).all()
        
        for attachment in attachments:
            db.delete(attachment)
        
        # Delete the session
        db.delete(session)
        db.commit()
        
        logger.info(f"Chat session deleted by admin: user={user_email}")
        
        return {
            "status": "deleted",
            "user": user_email,
            "message": f"Chat session deleted for {user_email}"
        }
    
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid session ID")
    
@router.post("/debug-search")
async def debug_search_endpoint(
    query: str,
    company_id: str,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Debug endpoint to test search without threshold filtering"""
    try:
        import json
        debug_result = chat_search_service.debug_search(
            query=query,
            company_id=UUID(company_id),
            min_similarity=0.0
        )
        logger.info(f"DEBUG SEARCH: {json.dumps(debug_result, indent=2)}")
        return debug_result
    except Exception as e:
        logger.error(f"Debug search error: {e}", exc_info=True)
        return {"error": str(e)}