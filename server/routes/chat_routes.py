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
from services.ticket_resolution_service import TicketResolutionService
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
    """Handle incoming Telegram messages."""
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
        
        # Handle photo messages
        elif photo:
            logger.info(f"Handling photo message with {len(photo)} photo(s), caption={bool(caption)}")
            response = await _handle_photo_message(
                photo=photo,
                chat_session=chat_session,
                message=message,
                db=db
            )
        
        # Handle document messages
        elif document:
            logger.info(f"Handling document message: {document.get('file_name')}, caption={bool(caption)}")
            response = await _handle_document_message(
                document=document,
                chat_session=chat_session,
                message=message,
                db=db
            )
        
        # Handle caption-only
        elif caption:
            logger.info(f"Handling caption-only message ({len(caption)} chars)")
            response = await _handle_text_message(
                text=caption,
                chat_session=chat_session,
                db=db
            )
        
        else:
            logger.warning("Message has no content")
        
        if response:
            logger.info(f"Sending response: {response[:100]}...")
            await _send_telegram_message(chat_id=chat_id, text=response)
        
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
        resolution_check_mode = state.get("resolution_check_mode", False)
        ticket_details_mode = state.get("ticket_details_mode", False)
        awaiting_category = state.get("awaiting_category", False)
        
        logger.info(
            f"State: waiting={waiting_for_confirmation}, resolution={resolution_check_mode}, "
            f"details={ticket_details_mode}, category={awaiting_category}"
        )
        
        # ============================================================
        # STATE: User is viewing similar tickets and selecting one
        # ============================================================
        if resolution_check_mode and state.get("similar_ticket_refs"):
            logger.info(f"Resolution check mode. User input: '{text}'")
            response_lower = text.lower().strip()
            
            # Retrieve tickets from cache
            similar_tickets = TicketResolutionService.get_cached_similar_tickets(
                str(chat_session.id)
            )
            
            if not similar_tickets:
                logger.warning("Similar tickets cache expired or empty")
                chat_session.session_state["resolution_check_mode"] = False
                flag_modified(chat_session, "session_state")
                db.commit()
                return "The search results have expired. Please send your issue again."
            
            logger.info(f"Retrieved {len(similar_tickets)} cached tickets")
            
            # Check for decline (no / create new / etc.)
            decline_words = ['no', 'nope', 'nah', 'false', 'create new', 'skip', 'none', 'different', 'other']
            if any(word in response_lower for word in decline_words):
                logger.info("User declined similar tickets, creating new ticket with inferred category")
                
                # Get inferred category from pending analysis
                pending_analysis = state.get("pending_analysis", {})
                inferred_category = pending_analysis.get("inferred_category", "other")
                original_issue = state.get("pending_issue", "Support issue")
                
                # Clear cache
                TicketResolutionService.clear_cached_similar_tickets(str(chat_session.id))
                
                try:
                    ticket = chat_ticket_service.create_ticket_from_chat(
                        chat_session_id=chat_session.id,
                        issue_description=original_issue,
                        inferred_category=inferred_category
                    )
                    
                    if not ticket:
                        chat_session.session_state["resolution_check_mode"] = False
                        flag_modified(chat_session, "session_state")
                        db.commit()
                        return "❌ Failed to create ticket after multiple attempts. Please try again."
                    
                    # Clear all states
                    chat_session.session_state["resolution_check_mode"] = False
                    chat_session.session_state["similar_ticket_refs"] = None
                    chat_session.session_state["ticket_details_mode"] = False
                    chat_session.session_state["pending_issue"] = None
                    chat_session.session_state["pending_analysis"] = None
                    flag_modified(chat_session, "session_state")
                    db.commit()
                    
                    logger.info(f"✓ Ticket created: {ticket.get('ticket_no')}")
                    
                    return (
                        f"✅ **Ticket Created!**\n\n"
                        f"🎫 Ticket Number: **{ticket.get('ticket_no')}**\n"
                        f"📌 Subject: {original_issue[:80]}...\n"
                        f"📂 Category: {inferred_category}\n\n"
                        f"Your support request has been submitted. Our team will review it shortly.\n\n"
                        f"Is there anything else I can help you with?"
                    )
                
                except Exception as e:
                    logger.error(f"Error creating ticket: {e}", exc_info=True)
                    chat_session.session_state["resolution_check_mode"] = False
                    flag_modified(chat_session, "session_state")
                    db.commit()
                    return f"❌ Failed to create ticket: {str(e)}"
            
            # Check for ticket number selection (1, 2, 3)
            if text.isdigit():
                ticket_idx = int(text) - 1
                logger.info(f"User selected ticket index: {ticket_idx}")
                
                if 0 <= ticket_idx < len(similar_tickets):
                    selected_ticket = similar_tickets[ticket_idx]
                    logger.info(f"Selected ticket: {selected_ticket.get('ticket_no')}")
                    
                    # Store selected ticket info
                    chat_session.session_state["ticket_details_mode"] = True
                    chat_session.session_state["selected_ticket_idx"] = ticket_idx
                    chat_session.session_state["selected_ticket_id"] = selected_ticket["ticket_id"]
                    flag_modified(chat_session, "session_state")
                    db.commit()
                    
                    # Return ticket details
                    details_message = TicketResolutionService.format_ticket_details_for_telegram(
                        selected_ticket
                    )
                    return details_message
                else:
                    logger.warning(f"Invalid ticket index: {ticket_idx}")
                    return f"Please select a valid ticket number (1-{len(similar_tickets)})"
            
            # Check for confirmation (yes)
            confirmation_words = ['yes', 'y', 'confirmed', 'works', 'solved', 'perfect', 'thanks', 'that\'s it']
            if any(word in response_lower for word in confirmation_words):
                logger.info("User confirmed issue is resolved")
                
                # Clear all states
                TicketResolutionService.clear_cached_similar_tickets(str(chat_session.id))
                chat_session.session_state["resolution_check_mode"] = False
                chat_session.session_state["similar_ticket_refs"] = None
                chat_session.session_state["ticket_details_mode"] = False
                chat_session.session_state["waiting_for_confirmation"] = False
                chat_session.session_state["pending_issue"] = None
                flag_modified(chat_session, "session_state")
                db.commit()
                
                return (
                    "✅ Excellent! Your issue is resolved.\n\n"
                    "📝 **For your records:**\n"
                    "• Keep the ticket number for future reference\n"
                    "• If you have more questions, just send a message\n\n"
                    "Thank you for using Gatekeeper! 🚀"
                )
            
            # Invalid input - ask again
            ticket_refs = state.get("similar_ticket_refs", [])
            return (
                "Please select an option:\n"
                f"• Reply with **number** (1-{len(ticket_refs)}) for full details\n"
                "• Reply **'yes'** if this resolves it\n"
                "• Reply **'no'** to create a new ticket"
            )
        
        # ============================================================
        # STATE: User is viewing ticket details
        # ============================================================
        if ticket_details_mode:
            logger.info(f"Ticket details mode. User input: '{text}'")
            response_lower = text.lower().strip()
            
            # Check for confirmation
            confirmation_words = ['yes', 'y', 'works', 'solved', 'thanks', 'perfect']
            if any(word in response_lower for word in confirmation_words):
                logger.info("User confirmed ticket resolved their issue")
                
                # Clear all states
                TicketResolutionService.clear_cached_similar_tickets(str(chat_session.id))
                chat_session.session_state["resolution_check_mode"] = False
                chat_session.session_state["ticket_details_mode"] = False
                chat_session.session_state["similar_ticket_refs"] = None
                flag_modified(chat_session, "session_state")
                db.commit()
                
                return (
                    "✅ Great! Your issue is resolved.\n\n"
                    "Thank you for using Gatekeeper! If you have more questions, just reach out. 🚀"
                )
            
            # Check for decline
            decline_words = ['no', 'doesn\'t work', 'more help', 'create new']
            if any(word in response_lower for word in decline_words):
                logger.info("User needs different solution")
                
                # Retrieve cached tickets
                similar_tickets = TicketResolutionService.get_cached_similar_tickets(
                    str(chat_session.id)
                )
                
                chat_session.session_state["ticket_details_mode"] = False
                flag_modified(chat_session, "session_state")
                db.commit()
                
                if similar_tickets and len(similar_tickets) > 1:
                    list_msg = TicketResolutionService.format_similar_tickets_for_telegram(similar_tickets)
                    return f"Let me show you the other similar tickets:\n\n{list_msg}"
                else:
                    # Create ticket with inferred category
                    pending_analysis = state.get("pending_analysis", {})
                    inferred_category = pending_analysis.get("inferred_category", "other")
                    original_issue = state.get("pending_issue", "Support issue")
                    
                    try:
                        ticket = chat_ticket_service.create_ticket_from_chat(
                            chat_session_id=chat_session.id,
                            issue_description=original_issue,
                            inferred_category=inferred_category
                        )
                        
                        # Clear all states
                        chat_session.session_state["resolution_check_mode"] = False
                        chat_session.session_state["ticket_details_mode"] = False
                        chat_session.session_state["similar_ticket_refs"] = None
                        chat_session.session_state["pending_issue"] = None
                        chat_session.session_state["pending_analysis"] = None
                        flag_modified(chat_session, "session_state")
                        db.commit()
                        
                        logger.info(f"✓ Ticket created: {ticket.get('ticket_no')}")
                        
                        return (
                            f"✅ **Ticket Created!**\n\n"
                            f"🎫 Ticket Number: **{ticket.get('ticket_no')}**\n"
                            f"📌 Subject: {original_issue[:80]}...\n"
                            f"📂 Category: {inferred_category}\n\n"
                            f"Your support request has been submitted. Our team will review it shortly.\n\n"
                            f"Is there anything else I can help you with?"
                        )
                    except Exception as e:
                        logger.error(f"Error creating ticket: {e}", exc_info=True)
                        chat_session.session_state["ticket_details_mode"] = False
                        flag_modified(chat_session, "session_state")
                        db.commit()
                        return f"❌ Failed to create ticket: {str(e)}"
            
            # Default response
            return "Did this ticket help? Reply: yes / no / need more help"
        
        # ============================================================
        # STATE: User is confirming ticket creation
        # ============================================================
        if waiting_for_confirmation:
            logger.info(f"Ticket confirmation. User input: '{text}'")
            response_lower = text.lower().strip()
            
            # Check for confirmation
            if response_lower in ["yes", "y", "confirm", "create", "ok"]:
                logger.info("User confirmed ticket creation")
                
                pending_issue = state.get("pending_issue", "")
                pending_analysis = state.get("pending_analysis", {})
                inferred_category = pending_analysis.get("inferred_category", "other")
                
                try:
                    ticket_result = chat_ticket_service.create_ticket_from_chat(
                        chat_session_id=chat_session.id,
                        issue_description=pending_issue,
                        inferred_category=inferred_category
                    )
                    
                    # Clear pending state
                    chat_session.session_state["waiting_for_confirmation"] = False
                    chat_session.session_state["pending_issue"] = None
                    chat_session.session_state["pending_analysis"] = None
                    chat_session.session_state["resolution_check_mode"] = False
                    flag_modified(chat_session, "session_state")
                    db.commit()
                    
                    logger.info(f"✓ Ticket created: {ticket_result.get('ticket_no')}")
                    return (
                        f"✅ Ticket created: {ticket_result.get('ticket_no')}\n"
                        f"🏷️ Category: {ticket_result.get('inferred_category')}\n\n"
                        f"The issue is being analyzed. You'll receive updates. 🚀"
                    )
                
                except Exception as e:
                    logger.error(f"Error creating ticket: {e}")
                    chat_session.session_state["waiting_for_confirmation"] = False
                    flag_modified(chat_session, "session_state")
                    db.commit()
                    return f"❌ Failed to create ticket: {str(e)}"
            
            # Check for decline
            elif response_lower in ["no", "n", "cancel", "skip"]:
                logger.info("User declined ticket creation")
                chat_session.session_state["waiting_for_confirmation"] = False
                chat_session.session_state["pending_issue"] = None
                chat_session.session_state["pending_analysis"] = None
                flag_modified(chat_session, "session_state")
                db.commit()
                return "✓ Cancelled. Send another message to get started."
            
            else:
                return (
                    "Please confirm:\n"
                    "✅ Yes / Confirm / Create\n"
                    "❌ No / Cancel / Skip"
                )
        
        # ============================================================
        # NORMAL STATE: User is sending a regular message
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
        
        # ============================================================
        # NORMAL STATE: Long message - analyze and show similar tickets
        # ============================================================
        if len(text) >= 20:
            logger.info(f"Long message ({len(text)} chars): analyzing...")
            try:
                analysis = chat_ticket_service.analyze_issue_for_chat(
                    chat_session_id=chat_session.id,
                    issue_description=text
                )
                
                inferred_category = analysis.get("inferred_category", "other")
                adaptive_threshold = analysis.get("adaptive_threshold", 0.5)
                
                logger.info(f"Analysis: category={inferred_category}, confidence={adaptive_threshold:.0%}")
                
                response = (
                    f"📋 Issue: {text[:80]}...\n\n"
                    f"🏷️ Category: {inferred_category}\n"
                    f"📊 Confidence: {adaptive_threshold:.0%}\n\n"
                )
                
                # Get similar tickets by category
                similar_tickets_detailed = TicketResolutionService.get_similar_tickets_with_metadata(
                    ticket_id=None,
                    company_id=str(chat_session.company_id),
                    limit=3,
                    min_score=70,
                    db=db,
                    category_filter=inferred_category
                )
                
                if similar_tickets_detailed:
                    logger.info(f"Found {len(similar_tickets_detailed)} similar tickets")
                    
                    # Filter out empty/invalid tickets
                    valid_tickets = [t for t in similar_tickets_detailed if t.get("ticket_no") and t.get("ticket_no") != "N/A"]
                    
                    if not valid_tickets:
                        logger.warning("No valid tickets after filtering, creating ticket with inferred category")
                        # No valid tickets - create ticket directly with inferred category
                        ticket = await _create_ticket_with_retry(
                            chat_ticket_service=chat_ticket_service,
                            chat_session_id=chat_session.id,
                            issue_description=text,
                            inferred_category=inferred_category,
                            db=db,
                            max_retries=3
                        )
                        
                        if not ticket:
                            return "❌ Failed to create ticket after multiple attempts. Please try again."
                        
                        # Clear all states
                        chat_session.session_state["resolution_check_mode"] = False
                        chat_session.session_state["pending_issue"] = None
                        chat_session.session_state["pending_analysis"] = None
                        flag_modified(chat_session, "session_state")
                        db.commit()
                        
                        return (
                            f"✅ **Ticket Created!**\n\n"
                            f"🎫 Ticket Number: **{ticket.get('ticket_no')}**\n"
                            f"📌 Subject: {text[:80]}...\n"
                            f"📂 Category: {inferred_category}\n"
                            f"📊 Confidence: {adaptive_threshold:.0%}\n\n"
                            f"Your support request has been submitted. Our team will review it shortly.\n\n"
                            f"Is there anything else I can help you with?"
                        )
                    
                    logger.info(f"Found {len(valid_tickets)} valid similar tickets")
                    
                    # Cache tickets
                    TicketResolutionService.cache_similar_tickets_for_session(
                        str(chat_session.id),
                        valid_tickets
                    )
                    
                    # Store metadata refs
                    ticket_refs = [
                        {
                            "ticket_no": t["ticket_no"],
                            "similarity_score": t["similarity_score"],
                            "ticket_id": t["ticket_id"]
                        }
                        for t in valid_tickets
                    ]
                    
                    chat_session.session_state["similar_ticket_refs"] = ticket_refs
                    chat_session.session_state["resolution_check_mode"] = True
                    chat_session.session_state["pending_issue"] = text
                    chat_session.session_state["pending_analysis"] = {
                        "inferred_category": inferred_category,
                        "adaptive_threshold": adaptive_threshold
                    }
                    flag_modified(chat_session, "session_state")
                    db.commit()
                    
                    # Format and show ticket list
                    similar_msg = TicketResolutionService.format_similar_tickets_for_telegram(
                        valid_tickets
                    )
                    response += similar_msg
                
                else:
                    logger.info("No similar tickets found, creating ticket with inferred category")
                    # No similar tickets - create ticket directly with inferred category
                    ticket = await _create_ticket_with_retry(
                        chat_ticket_service=chat_ticket_service,
                        chat_session_id=chat_session.id,
                        issue_description=text,
                        inferred_category=inferred_category,
                        db=db,
                        max_retries=3
                    )
                    
                    if not ticket:
                        return "❌ Failed to create ticket after multiple attempts. Please try again."
                    
                    # Clear all states
                    chat_session.session_state["resolution_check_mode"] = False
                    chat_session.session_state["pending_issue"] = None
                    chat_session.session_state["pending_analysis"] = None
                    flag_modified(chat_session, "session_state")
                    db.commit()
                    
                    return (
                        f"✅ **Ticket Created!**\n\n"
                        f"🎫 Ticket Number: **{ticket.get('ticket_no')}**\n"
                        f"📌 Subject: {text[:80]}...\n"
                        f"📂 Category: {inferred_category}\n"
                        f"📊 Confidence: {adaptive_threshold:.0%}\n\n"
                        f"Your support request has been submitted. Our team will review it shortly.\n\n"
                        f"Is there anything else I can help you with?"
                    )
                
                return response
            
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
                response += "\n\nSend a longer message (20+ chars) for more options."
                return response
            else:
                return "No solutions found. Send a longer message to explore options."
    
    except Exception as e:
        logger.error(f"Error handling text message: {e}", exc_info=True)
        return "❌ Error processing message. Please try again."


async def _handle_photo_message(
    photo: list,
    chat_session: ChatSession,
    message: Dict,
    db: Session
) -> Optional[str]:
    """Handle photo messages from Telegram"""
    
    try:
        # Get largest photo
        largest_photo = max(photo, key=lambda x: x.get("file_size", 0))
        file_id = largest_photo.get("file_id")
        
        if not file_id:
            return "Could not process photo"
        
        # Download photo
        file_path = await _download_telegram_file(file_id)
        
        if not file_path:
            return "Failed to download photo"
        
        # Store attachment
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
        
        # If caption provided and long enough, analyze
        if caption and len(caption) >= 10:
            logger.info(f"Photo with caption ({len(caption)} chars): analyzing...")
            try:
                issue_description = f"{caption}\n[Photo attached]"
                
                analysis = chat_ticket_service.analyze_issue_for_chat(
                    chat_session_id=chat_session.id,
                    issue_description=issue_description,
                    image_path=file_path
                )
                
                inferred_category = analysis.get("inferred_category", "other")
                adaptive_threshold = analysis.get("adaptive_threshold", 0.5)
                
                response = f"Issue: {caption[:80]}...\n\nCategory: {inferred_category}\nConfidence: {adaptive_threshold:.0%}\n\n"
                
                # Get similar tickets
                similar_tickets_detailed = TicketResolutionService.get_similar_tickets_with_metadata(
                    ticket_id=None,
                    company_id=str(chat_session.company_id),
                    limit=3,
                    min_score=70,
                    db=db,
                    category_filter=inferred_category
                )
                
                if similar_tickets_detailed:
                    valid_tickets = [t for t in similar_tickets_detailed if t.get("ticket_no") and t.get("ticket_no") != "N/A"]
                    
                    if valid_tickets:
                        logger.info(f"Found {len(valid_tickets)} valid similar tickets")
                        
                        # Cache tickets
                        TicketResolutionService.cache_similar_tickets_for_session(
                            str(chat_session.id),
                            valid_tickets
                        )
                        
                        ticket_refs = [
                            {
                                "ticket_no": t["ticket_no"],
                                "similarity_score": t["similarity_score"],
                                "ticket_id": t["ticket_id"]
                            }
                            for t in valid_tickets
                        ]
                        
                        chat_session.session_state["similar_ticket_refs"] = ticket_refs
                        chat_session.session_state["resolution_check_mode"] = True
                        chat_session.session_state["pending_issue"] = issue_description
                        chat_session.session_state["pending_analysis"] = {
                            "inferred_category": inferred_category,
                            "adaptive_threshold": adaptive_threshold
                        }
                        flag_modified(chat_session, "session_state")
                        db.commit()
                        
                        similar_msg = TicketResolutionService.format_similar_tickets_for_telegram(
                            valid_tickets
                        )
                        response += similar_msg
                    else:
                        # No valid tickets - create ticket with inferred category
                        try:
                            ticket = chat_ticket_service.create_ticket_from_chat(
                                chat_session_id=chat_session.id,
                                issue_description=issue_description,
                                inferred_category=inferred_category
                            )
                            
                            # Clear all states
                            chat_session.session_state["resolution_check_mode"] = False
                            chat_session.session_state["pending_issue"] = None
                            chat_session.session_state["pending_analysis"] = None
                            flag_modified(chat_session, "session_state")
                            db.commit()
                            
                            response += (
                                f"🔍 No existing solutions found.\n\n"
                                f"✅ **Ticket Created!**\n\n"
                                f"🎫 Ticket Number: **{ticket.get('ticket_no')}**\n"
                                f"📌 Subject: {issue_description[:80]}...\n"
                                f"📂 Category: {inferred_category}\n\n"
                                f"Your support request has been submitted. Our team will review it shortly."
                            )
                        except Exception as e:
                            logger.error(f"Error creating ticket: {e}", exc_info=True)
                            response += f"Error creating ticket: {str(e)}"
                else:
                    # No similar tickets - create ticket with inferred category
                    try:
                        ticket = chat_ticket_service.create_ticket_from_chat(
                            chat_session_id=chat_session.id,
                            issue_description=issue_description,
                            inferred_category=inferred_category
                        )
                        
                        # Clear all states
                        chat_session.session_state["resolution_check_mode"] = False
                        chat_session.session_state["pending_issue"] = None
                        chat_session.session_state["pending_analysis"] = None
                        flag_modified(chat_session, "session_state")
                        db.commit()
                        
                        response += (
                            f"🔍 No existing solutions found.\n\n"
                            f"✅ **Ticket Created!**\n\n"
                            f"🎫 Ticket Number: **{ticket.get('ticket_no')}**\n"
                            f"📌 Subject: {issue_description[:80]}...\n"
                            f"📂 Category: {inferred_category}\n\n"
                            f"Your support request has been submitted. Our team will review it shortly."
                        )
                    except Exception as e:
                        logger.error(f"Error creating ticket: {e}", exc_info=True)
                        response += f"Error creating ticket: {str(e)}"
                
                return response
            
            except Exception as e:
                logger.error(f"Error analyzing photo: {e}", exc_info=True)
                return "Error analyzing photo. Please try again."
        
        else:
            return "Photo received. Please describe your issue and I'll create a ticket."
    
    except Exception as e:
        logger.error(f"Error handling photo message: {e}")
        return "Error processing photo. Please try again."


async def _handle_document_message(
    document: dict,
    chat_session: ChatSession,
    message: Dict,
    db: Session
) -> Optional[str]:
    """Handle document messages from Telegram"""
    
    try:
        file_id = document.get("file_id")
        file_name = document.get("file_name", "document")
        
        if not file_id:
            return "Could not process document"
        
        # Download document
        file_path = await _download_telegram_file(file_id)
        
        if not file_path:
            return "Failed to download document"
        
        # Store attachment
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
        
        # If caption provided and long enough, analyze
        if caption and len(caption) >= 10:
            logger.info(f"Document with caption ({len(caption)} chars): analyzing...")
            try:
                issue_description = f"{caption}\n[Document: {file_name}]"
                
                analysis = chat_ticket_service.analyze_issue_for_chat(
                    chat_session_id=chat_session.id,
                    issue_description=issue_description,
                    image_path=file_path
                )
                
                inferred_category = analysis.get("inferred_category", "other")
                adaptive_threshold = analysis.get("adaptive_threshold", 0.5)
                
                response = f"Issue: {caption[:80]}...\n\nCategory: {inferred_category}\nConfidence: {adaptive_threshold:.0%}\n\n"
                
                # Get similar tickets
                similar_tickets_detailed = TicketResolutionService.get_similar_tickets_with_metadata(
                    ticket_id=None,
                    company_id=str(chat_session.company_id),
                    limit=3,
                    min_score=70,
                    db=db,
                    category_filter=inferred_category
                )
                
                if similar_tickets_detailed:
                    valid_tickets = [t for t in similar_tickets_detailed if t.get("ticket_no") and t.get("ticket_no") != "N/A"]
                    
                    if valid_tickets:
                        logger.info(f"Found {len(valid_tickets)} valid similar tickets")
                        
                        # Cache tickets
                        TicketResolutionService.cache_similar_tickets_for_session(
                            str(chat_session.id),
                            valid_tickets
                        )
                        
                        ticket_refs = [
                            {
                                "ticket_no": t["ticket_no"],
                                "similarity_score": t["similarity_score"],
                                "ticket_id": t["ticket_id"]
                            }
                            for t in valid_tickets
                        ]
                        
                        chat_session.session_state["similar_ticket_refs"] = ticket_refs
                        chat_session.session_state["resolution_check_mode"] = True
                        chat_session.session_state["pending_issue"] = issue_description
                        chat_session.session_state["pending_analysis"] = {
                            "inferred_category": inferred_category,
                            "adaptive_threshold": adaptive_threshold
                        }
                        flag_modified(chat_session, "session_state")
                        db.commit()
                        
                        similar_msg = TicketResolutionService.format_similar_tickets_for_telegram(
                            valid_tickets
                        )
                        response += similar_msg
                    else:
                        # No valid tickets - create ticket with inferred category
                        try:
                            ticket = chat_ticket_service.create_ticket_from_chat(
                                chat_session_id=chat_session.id,
                                issue_description=issue_description,
                                inferred_category=inferred_category
                            )
                            
                            # Clear all states
                            chat_session.session_state["resolution_check_mode"] = False
                            chat_session.session_state["pending_issue"] = None
                            chat_session.session_state["pending_analysis"] = None
                            flag_modified(chat_session, "session_state")
                            db.commit()
                            
                            response += (
                                f"🔍 No existing solutions found.\n\n"
                                f"✅ **Ticket Created!**\n\n"
                                f"🎫 Ticket Number: **{ticket.get('ticket_no')}**\n"
                                f"📌 Subject: {issue_description[:80]}...\n"
                                f"📂 Category: {inferred_category}\n\n"
                                f"Your support request has been submitted. Our team will review it shortly."
                            )
                        except Exception as e:
                            logger.error(f"Error creating ticket: {e}", exc_info=True)
                            response += f"Error creating ticket: {str(e)}"
                else:
                    # No similar tickets - create ticket with inferred category
                    try:
                        ticket = chat_ticket_service.create_ticket_from_chat(
                            chat_session_id=chat_session.id,
                            issue_description=issue_description,
                            inferred_category=inferred_category
                        )
                        
                        # Clear all states
                        chat_session.session_state["resolution_check_mode"] = False
                        chat_session.session_state["pending_issue"] = None
                        chat_session.session_state["pending_analysis"] = None
                        flag_modified(chat_session, "session_state")
                        db.commit()
                        
                        response += (
                            f"🔍 No existing solutions found.\n\n"
                            f"✅ **Ticket Created!**\n\n"
                            f"🎫 Ticket Number: **{ticket.get('ticket_no')}**\n"
                            f"📌 Subject: {issue_description[:80]}...\n"
                            f"📂 Category: {inferred_category}\n\n"
                            f"Your support request has been submitted. Our team will review it shortly."
                        )
                    except Exception as e:
                        logger.error(f"Error creating ticket: {e}", exc_info=True)
                        response += f"Error creating ticket: {str(e)}"
                
                return response
            
            except Exception as e:
                logger.error(f"Error analyzing document: {e}", exc_info=True)
                return "Error analyzing document. Please try again."
        
        else:
            return "Document received. Please describe your issue and I'll create a ticket."
    
    except Exception as e:
        logger.error(f"Error handling document message: {e}")
        return "Error processing document. Please try again."


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
    """Search for solutions (non-webhook endpoint for testing)"""
    
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
    """Record user feedback about search results"""
    
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


@router.post("/init")
@invalidate_on_mutation(tags=["chat:sessions"])
async def init_chat_session(
    user_id: str,
    telegram_chat_id: str,
    admin_payload: dict = Depends(get_current_admin),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Create a chat session for a user (admin only)"""
    try:
        # Get the user
        user = db.query(User).filter(User.id == UUID(user_id)).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Check if session already exists
        existing = db.query(ChatSession).filter(
            ChatSession.user_id == UUID(user_id)
        ).first()
        
        if existing:
            # Update existing session
            old_telegram_id = existing.telegram_chat_id
            existing.telegram_chat_id = str(telegram_chat_id)
            db.commit()
            
            logger.info(
                f"✓ Chat session updated: user={user.email}, "
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
        
        # Create new session
        chat_session = ChatSession(
            user_id=UUID(user_id),
            company_id=user.company_id,
            telegram_chat_id=str(telegram_chat_id),
            session_state={
                "initialized_by_admin": admin_payload.get("id"),
                "initialized_at": to_iso_date(datetime.utcnow()),
                "resolution_check_mode": False,
                "ticket_details_mode": False,
                "awaiting_category": False,
                "similar_ticket_refs": None,
                "waiting_for_confirmation": False,
                "pending_issue": None,
                "pending_analysis": None
            }
        )
        
        db.add(chat_session)
        db.commit()
        
        logger.info(f"✓ Chat session created: user={user.email}, company={user.company.name}")
        
        return {
            "status": "created",
            "session_id": str(chat_session.id),
            "user": user.email,
            "company": user.company.name,
            "telegram_chat_id": str(telegram_chat_id),
            "message": f"✓ Chat session created for {user.email}"
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
    """List all chat sessions (admin only)"""
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
    """Delete a chat session (admin only)"""
    try:
        session = db.query(ChatSession).filter(
            ChatSession.id == UUID(session_id)
        ).first()
        
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        user_email = session.user.email
        
        # Delete attachments
        attachments = db.query(ChatAttachment).filter(
            ChatAttachment.chat_session_id == UUID(session_id)
        ).all()
        
        for attachment in attachments:
            db.delete(attachment)
        
        # Delete session
        db.delete(session)
        db.commit()
        
        logger.info(f"Chat session deleted: user={user_email}")
        
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
    """Debug endpoint to test search"""
    try:
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


# ==================== HELPER FUNCTIONS ====================

def _get_help_message() -> str:
    """Get help message"""
    return """🤖 Gatekeeper Chat Assistant

Commands:
/help - Show this message
/status - View your chat session status
/search <query> - Search for similar issues

Or just send a message:
• Short message (< 20 chars) → Search for similar issues
• Long message (≥ 20 chars) → Show similar tickets + create new

📸 You can also share screenshots - add a description!
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

Session state keys: {list(chat_session.session_state.keys()) if chat_session.session_state else 'empty'}
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
    
async def _create_ticket_with_retry(
    chat_ticket_service: ChatTicketService,
    chat_session_id: UUID,
    issue_description: str,
    inferred_category: str,
    db: Session,
    max_retries: int = 3
) -> Optional[Dict[str, Any]]:
    """
    Create ticket with retry logic for duplicate ticket_no errors.
    
    Uses TicketCreationService.get_next_ticket_number() for sequential numbering.
    Handles race conditions with database-level locking and exponential backoff.
    """
    
    import asyncio
    from services.ticket_creation_service import TicketCreationService
    
    for attempt in range(max_retries):
        try:
            # Get next sequential ticket number (uses advisory lock)
            ticket_no = TicketCreationService.get_next_ticket_number()
            logger.info(f"Attempt {attempt + 1}: Generated ticket number {ticket_no}")
            
            # Set transaction isolation level
            db.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
            
            # Create ticket using the generated number
            ticket = chat_ticket_service.create_ticket_from_chat(
                chat_session_id=chat_session_id,
                issue_description=issue_description,
                inferred_category=inferred_category,
                ticket_no=ticket_no  # Pass the sequential number
            )
            
            if not ticket:
                logger.error(f"Ticket creation returned None despite no exception")
                db.rollback()
                # Retry on unexpected None
                if attempt < max_retries - 1:
                    await asyncio.sleep(0.1 * (2 ** attempt))
                    continue
                return None
            
            logger.info(f"✓ Ticket created on attempt {attempt + 1}: {ticket.get('ticket_no')}")
            return ticket
        
        except Exception as e:
            error_msg = str(e)
            logger.warning(f"Attempt {attempt + 1} failed: {error_msg}")
            
            db.rollback()
            
            # Check if it's a duplicate ticket_no error (shouldn't happen with lock, but handle it)
            if "duplicate key value violates unique constraint" in error_msg and "ticket_no" in error_msg:
                logger.warning(f"Duplicate ticket_no detected on attempt {attempt + 1}")
                if attempt < max_retries - 1:
                    # Exponential backoff: 0.1s, 0.2s, 0.4s
                    wait_time = 0.1 * (2 ** attempt)
                    logger.info(f"Retrying in {wait_time}s...")
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    logger.error(f"Failed after {max_retries} attempts")
                    return None
            else:
                # Different error - log and don't retry
                logger.error(f"Non-retryable error: {error_msg}")
                return None
    
    return None