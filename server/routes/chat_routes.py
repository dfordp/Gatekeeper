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
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.orm.attributes import flag_modified

from core.database import (
    get_db, ChatSession, User, Company, Ticket, ChatAttachment, TicketEvent
)
from core.config import TELEGRAM_BOT_TOKEN, TELEGRAM_API
from middleware.cache_decorator import cache_endpoint, invalidate_on_mutation
from services.chat_ticket_service import ChatTicketService
from services.chat_search_service import ChatSearchService
from services.ticket_resolution_service import TicketResolutionService, _build_ticket_dict
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
                db=db,
                chat_id=chat_id,
            )

        # Handle photo messages
        elif photo:
            logger.info(f"Handling photo message with {len(photo)} photo(s), caption={bool(caption)}")
            response = await _handle_photo_message(
                photo=photo,
                chat_session=chat_session,
                message=message,
                db=db,
            )

        # Handle document messages
        elif document:
            logger.info(f"Handling document message: {document.get('file_name')}, caption={bool(caption)}")
            response = await _handle_document_message(
                document=document,
                chat_session=chat_session,
                message=message,
                db=db,
            )

        # Handle caption-only
        elif caption:
            logger.info(f"Handling caption-only message ({len(caption)} chars)")
            response = await _handle_text_message(
                text=caption,
                chat_session=chat_session,
                db=db,
                chat_id=chat_id,
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


import re as _re


def _build_ticket_subject(user_message: Optional[str], analysis: Dict[str, Any]) -> str:
    """Extract a clean one-line subject for the ticket."""
    vision_context = analysis.get("vision_context", "")

    # Prefer the exact error title quoted in the vision output
    if vision_context:
        quoted = _re.findall(r'"([^"]{10,120})"', vision_context)
        if quoted:
            return quoted[0]

        # Look for ERROR_TITLE: line from the structured prompt
        match = _re.search(r'ERROR_TITLE:\s*"?([^"\n]{10,120})"?', vision_context, _re.IGNORECASE)
        if match:
            return match.group(1).strip()

    # Fall back to Groq's extracted issue description (usually cleaner than raw user text)
    groq_issue = analysis.get("groq_entities", {}).get("issue_description", "")
    if groq_issue and len(groq_issue.strip()) >= 10:
        return groq_issue.strip()[:120]

    # Last resort: user's own message
    if user_message and len(user_message.strip()) >= 5:
        return user_message.strip()[:120]

    return "Support request"


def _build_ticket_description(
    user_message: Optional[str],
    analysis: Dict[str, Any],
    image_attached: bool = False,
) -> str:
    """Build a clean, team-readable description from user input + vision extraction."""
    parts = []

    # 1. User's own words
    if user_message and user_message.strip():
        parts.append(f"Reported by user:\n{user_message.strip()}")

    # 2. Structured error details from vision (parse the structured output)
    vision_context = analysis.get("vision_context", "")
    if vision_context:
        detail_lines = []
        for field in ("APPLICATION", "ERROR_TITLE", "ERROR_BODY", "SERVER", "ACTION"):
            match = _re.search(
                rf'{field}:\s*(.+)',
                vision_context,
                _re.IGNORECASE
            )
            if match:
                value = match.group(1).strip().strip('"')
                if value and value.lower() not in ("n/a", "none", "unknown", "-"):
                    label = field.replace("_", " ").title()
                    detail_lines.append(f"  {label}: {value}")

        if detail_lines:
            parts.append("Error details (from screenshot):\n" + "\n".join(detail_lines))

    # 3. Screenshot note
    if image_attached:
        parts.append("Screenshot attached.")

    if not parts:
        # Absolute fallback — should not normally happen
        groq_issue = analysis.get("groq_entities", {}).get("issue_description", "")
        return groq_issue or "Support issue reported via chat."

    return "\n\n".join(parts)


async def _run_issue_analysis(
    issue_description: str,
    chat_session: ChatSession,
    db: Session,
    image_path: Optional[str] = None,
    image_paths: Optional[list] = None,
    user_message: Optional[str] = None,
    pre_extracted_vision: Optional[str] = None,
) -> str:
    """
    Shared: analyze an issue description, search for similar resolved tickets,
    update session state, and return a conversational response.
    """
    # Resolve all image paths (support single or multiple)
    all_image_paths = image_paths or ([image_path] if image_path else [])
    primary_image = all_image_paths[0] if all_image_paths else None

    analysis = chat_ticket_service.analyze_issue_for_chat(
        chat_session_id=chat_session.id,
        issue_description=issue_description,
        # Skip re-extraction if vision was already done in the photo handler
        image_path=None if pre_extracted_vision else primary_image,
        vision_context=pre_extracted_vision,
    )

    inferred_category = analysis.get("inferred_category", "other")

    # Build full ticket metadata directly from Qdrant results — no LLM, no category filter
    qdrant_results = analysis.get("similar_solutions", [])
    similar_tickets_detailed = []
    for r in qdrant_results:
        tid = r.get("ticket_id")
        if not tid:
            continue
        ticket_obj = (
            db.query(Ticket)
            .options(joinedload(Ticket.raised_by_user))
            .filter(Ticket.id == UUID(tid))
            .first()
        )
        if not ticket_obj:
            continue
        score_int = int(round(r.get("similarity_score", 0) * 100))
        ticket_dict = _build_ticket_dict(ticket_obj, score_int, db)
        if ticket_dict.get("ticket_no") and ticket_dict["ticket_no"] != "N/A":
            similar_tickets_detailed.append(ticket_dict)

    valid_tickets = similar_tickets_detailed

    if not valid_tickets:
        subject = _build_ticket_subject(user_message, analysis)
        description = _build_ticket_description(
            user_message=user_message,
            analysis=analysis,
            image_attached=bool(all_image_paths),
        )
        ticket = await _create_ticket_with_retry(
            chat_ticket_service=chat_ticket_service,
            chat_session_id=chat_session.id,
            issue_description=description,
            inferred_category=inferred_category,
            db=db,
            max_retries=3,
            subject=subject,
            image_paths=all_image_paths,
        )

        if not ticket:
            return "I wasn't able to create a ticket just now — please try again in a moment."

        chat_session.session_state["resolution_check_mode"] = False
        chat_session.session_state["pending_issue"] = None
        chat_session.session_state["pending_analysis"] = None
        flag_modified(chat_session, "session_state")
        db.commit()

        return (
            f"I couldn't find any similar past issues, so I've raised ticket "
            f"{ticket.get('ticket_no')} for you. The support team will be in touch shortly."
        )

    TicketResolutionService.cache_similar_tickets_for_session(str(chat_session.id), valid_tickets)

    ticket_refs = [
        {"ticket_no": t["ticket_no"], "similarity_score": t["similarity_score"], "ticket_id": t["ticket_id"]}
        for t in valid_tickets
    ]

    chat_session.session_state["similar_ticket_refs"] = ticket_refs
    chat_session.session_state["resolution_check_mode"] = True
    chat_session.session_state["pending_issue"] = issue_description
    chat_session.session_state["pending_analysis"] = {
        "inferred_category": inferred_category,
        "adaptive_threshold": analysis.get("adaptive_threshold", 0.5),
        "user_message": user_message or "",
        "image_paths": all_image_paths,
    }
    flag_modified(chat_session, "session_state")
    db.commit()

    return TicketResolutionService.format_similar_tickets_for_telegram(valid_tickets)


async def _handle_text_message(
    text: str,
    chat_session: ChatSession,
    db: Session,
    chat_id: Optional[int] = None,
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
                logger.warning("Cache expired — recovering from session state")
                pending_analysis = state.get("pending_analysis", {})
                inferred_category = pending_analysis.get("inferred_category")
                if inferred_category:
                    similar_tickets = TicketResolutionService.get_similar_tickets_with_metadata(
                        ticket_id=None,
                        company_id=str(chat_session.company_id),
                        limit=3,
                        min_score=70,
                        db=db,
                        category_filter=inferred_category
                    )
                    if similar_tickets:
                        TicketResolutionService.cache_similar_tickets_for_session(
                            str(chat_session.id), similar_tickets
                        )
                        chat_session.session_state["similar_ticket_refs"] = [
                            {"ticket_no": t["ticket_no"], "similarity_score": t["similarity_score"], "ticket_id": t["ticket_id"]}
                            for t in similar_tickets
                        ]
                        flag_modified(chat_session, "session_state")
                        db.commit()

            if not similar_tickets:
                chat_session.session_state["resolution_check_mode"] = False
                flag_modified(chat_session, "session_state")
                db.commit()
                return "I seem to have lost those results — could you describe your issue again and I'll search fresh?"
            
            logger.info(f"Retrieved {len(similar_tickets)} cached tickets")
            
            # Check for decline (no / create new / etc.)
            decline_words = ['no', 'nope', 'nah', 'false', 'create new', 'skip', 'none', 'different', 'other']
            if any(word in response_lower for word in decline_words):
                logger.info("User declined similar tickets, creating new ticket with inferred category")
                
                # Get inferred category from pending analysis
                pending_analysis = state.get("pending_analysis", {})
                inferred_category = pending_analysis.get("inferred_category", "other")
                original_issue = state.get("pending_issue", "Support issue")
                saved_user_message = pending_analysis.get("user_message") or None
                saved_image_paths = pending_analysis.get("image_paths") or []

                # Clear cache
                TicketResolutionService.clear_cached_similar_tickets(str(chat_session.id))

                try:
                    ticket = chat_ticket_service.create_ticket_from_chat(
                        chat_session_id=chat_session.id,
                        issue_description=original_issue,
                        inferred_category=inferred_category,
                        subject=saved_user_message[:120] if saved_user_message else None,
                        image_paths=saved_image_paths,
                    )
                    
                    if not ticket:
                        chat_session.session_state["resolution_check_mode"] = False
                        flag_modified(chat_session, "session_state")
                        db.commit()
                        return "I wasn't able to create a ticket just now — please try again in a moment."
                    
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
                        f"Done — I've raised ticket {ticket.get('ticket_no')} for you. "
                        f"The support team will review it and be in touch shortly."
                    )

                except Exception as e:
                    logger.error(f"Error creating ticket: {e}", exc_info=True)
                    chat_session.session_state["resolution_check_mode"] = False
                    flag_modified(chat_session, "session_state")
                    db.commit()
                    return "Something went wrong creating your ticket — please try again."

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
                    
                    # Return ticket details and send any attachments
                    details_message = TicketResolutionService.format_ticket_details_for_telegram(
                        selected_ticket
                    )

                    # Send attachment files via Telegram after the text
                    if chat_id:
                        all_atts = (
                            selected_ticket.get("attachments", [])
                            + selected_ticket.get("rca_attachments", [])
                        )
                        for att in all_atts[:5]:
                            fp = att.get("url") or att.get("file_path")
                            if fp:
                                await _send_telegram_file(
                                    chat_id=chat_id,
                                    file_path=fp,
                                    file_name=att.get("name", "attachment"),
                                    mime_type=att.get("mime_type"),
                                )

                    return details_message
                else:
                    logger.warning(f"Invalid ticket index: {ticket_idx}")
                    return f"Please select a valid ticket number (1-{len(similar_tickets)})"
            
            # Check for confirmation (yes)
            confirmation_words = ['yes', 'y', 'confirmed', 'works', 'solved', 'perfect', 'thanks', 'that\'s it']
            if any(word in response_lower for word in confirmation_words):
                logger.info("User confirmed issue is resolved")

                TicketResolutionService.clear_cached_similar_tickets(str(chat_session.id))
                chat_session.session_state["resolution_check_mode"] = False
                chat_session.session_state["similar_ticket_refs"] = None
                chat_session.session_state["ticket_details_mode"] = False
                chat_session.session_state["waiting_for_confirmation"] = False
                chat_session.session_state["pending_issue"] = None
                flag_modified(chat_session, "session_state")
                db.commit()

                return "Great, glad that helped! Feel free to message if anything else comes up."

            # Invalid input - ask again
            ticket_refs = state.get("similar_ticket_refs", [])
            return (
                f"Reply with a number (1–{len(ticket_refs)}) to see the full details, "
                "'yes' if one of these resolves your issue, or 'no' to open a new ticket."
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

                TicketResolutionService.clear_cached_similar_tickets(str(chat_session.id))
                chat_session.session_state["resolution_check_mode"] = False
                chat_session.session_state["ticket_details_mode"] = False
                chat_session.session_state["similar_ticket_refs"] = None
                flag_modified(chat_session, "session_state")
                db.commit()

                return "Glad that sorted it out! Message me if anything else comes up."
            
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
                    saved_user_message = pending_analysis.get("user_message") or None
                    saved_image_paths = pending_analysis.get("image_paths") or []

                    try:
                        ticket = chat_ticket_service.create_ticket_from_chat(
                            chat_session_id=chat_session.id,
                            issue_description=original_issue,
                            inferred_category=inferred_category,
                            subject=saved_user_message[:120] if saved_user_message else None,
                            image_paths=saved_image_paths,
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
                            f"Done — I've raised ticket {ticket.get('ticket_no')} for you. "
                            f"The support team will take a look and be in touch."
                        )
                    except Exception as e:
                        logger.error(f"Error creating ticket: {e}", exc_info=True)
                        chat_session.session_state["ticket_details_mode"] = False
                        flag_modified(chat_session, "session_state")
                        db.commit()
                        return "Something went wrong creating your ticket — please try again."

            # Default response
            return "Did that help? Reply yes, no, or 'need more help'."
        
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
                saved_user_message = pending_analysis.get("user_message") or None
                saved_image_paths = pending_analysis.get("image_paths") or []

                try:
                    ticket_result = chat_ticket_service.create_ticket_from_chat(
                        chat_session_id=chat_session.id,
                        issue_description=pending_issue,
                        inferred_category=inferred_category,
                        subject=saved_user_message[:120] if saved_user_message else None,
                        image_paths=saved_image_paths,
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
                        f"Done — ticket {ticket_result.get('ticket_no')} has been raised. "
                        f"The support team will review it and get back to you shortly."
                    )

                except Exception as e:
                    logger.error(f"Error creating ticket: {e}")
                    chat_session.session_state["waiting_for_confirmation"] = False
                    flag_modified(chat_session, "session_state")
                    db.commit()
                    return "Something went wrong creating your ticket — please try again in a moment."

            # Check for decline
            elif response_lower in ["no", "n", "cancel", "skip"]:
                logger.info("User declined ticket creation")
                chat_session.session_state["waiting_for_confirmation"] = False
                chat_session.session_state["pending_issue"] = None
                chat_session.session_state["pending_analysis"] = None
                flag_modified(chat_session, "session_state")
                db.commit()
                return "No problem. Send a message whenever you're ready."

            else:
                return "Just reply 'yes' to confirm or 'no' to cancel."
        
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

            # Consume any pending screenshots sent before this message
            pending_files = list(chat_session.session_state.get("pending_files") or [])
            pending_vision = list(chat_session.session_state.get("pending_vision") or [])

            if pending_files:
                combined_vision = "\n\n".join(pending_vision) if pending_vision else ""
                issue_description = (
                    f"{text}\n\nFrom screenshots:\n{combined_vision}"
                    if combined_vision else text
                )
                chat_session.session_state["pending_files"] = []
                chat_session.session_state["pending_vision"] = []
                flag_modified(chat_session, "session_state")
            else:
                combined_vision = ""
                issue_description = text
                pending_files = []

            try:
                return await _run_issue_analysis(
                    issue_description=issue_description,
                    chat_session=chat_session,
                    db=db,
                    image_paths=pending_files if pending_files else None,
                    user_message=text,
                    pre_extracted_vision=combined_vision or None,
                )
            except Exception as e:
                logger.error(f"Error analyzing issue: {e}", exc_info=True)
                return "Something went wrong while looking that up — please try again."

        else:
            # Short message - search only
            logger.info(f"Short message ({len(text)} chars): search only")
            results = chat_search_service.search_for_solutions(
                query=text,
                company_id=chat_session.company_id,
                limit=3
            )

            if results:
                response = "Here are a few similar issues I found:\n"
                response += _format_search_results(results)
                response += "\n\nGive me a bit more detail and I can dig deeper."
                return response
            else:
                return "Nothing matched on that — try describing what's happening in a bit more detail."
    
    except Exception as e:
        logger.error(f"Error handling text message: {e}", exc_info=True)
        return "Something went wrong — please try again."


async def _handle_photo_message(
    photo: list,
    chat_session: ChatSession,
    message: Dict,
    db: Session
) -> Optional[str]:
    """Handle photo messages from Telegram, always using vision AI."""

    try:
        largest_photo = max(photo, key=lambda x: x.get("file_size", 0))
        file_id = largest_photo.get("file_id")

        if not file_id:
            return "I couldn't process that photo — could you try sending it again?"

        file_path = await _download_telegram_file(file_id)

        if not file_path:
            return "The photo download failed — please try again or describe your issue in text."

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

        caption = message.get("caption", "").strip()

        # Always run vision analysis
        vision_context = None
        try:
            vision_context = chat_ticket_service._extract_vision_context(file_path)
            if vision_context:
                logger.info(f"Vision analysis complete ({len(vision_context)} chars)")
        except Exception as e:
            logger.warning(f"Vision analysis failed: {e}")

        # Accumulate into session pending lists for multi-attachment support
        pending_files = list(chat_session.session_state.get("pending_files") or [])
        pending_vision = list(chat_session.session_state.get("pending_vision") or [])

        pending_files.append(file_path)
        if vision_context:
            pending_vision.append(vision_context)

        chat_session.session_state["pending_files"] = pending_files
        chat_session.session_state["pending_vision"] = pending_vision
        flag_modified(chat_session, "session_state")
        db.commit()

        count = len(pending_files)

        # If caption is long enough, process everything now
        if caption and len(caption) >= 10:
            combined_vision = "\n\n".join(pending_vision) if pending_vision else ""
            issue_description = (
                f"{caption}\n\nFrom screenshots:\n{combined_vision}"
                if combined_vision else caption
            )

            # Clear accumulators before analysis
            chat_session.session_state["pending_files"] = []
            chat_session.session_state["pending_vision"] = []
            flag_modified(chat_session, "session_state")

            try:
                return await _run_issue_analysis(
                    issue_description=issue_description,
                    chat_session=chat_session,
                    db=db,
                    image_paths=pending_files,
                    user_message=caption,
                    pre_extracted_vision=combined_vision or None,
                )
            except Exception as e:
                logger.error(f"Error analyzing photo: {e}", exc_info=True)
                return "Something went wrong analyzing that screenshot — could you describe what you're seeing?"

        # No caption — hint at what was found and wait for user's description
        import re as _re2
        error_hint = ""
        if vision_context:
            quoted = _re2.findall(r'"([^"]{10,100})"', vision_context)
            if quoted:
                error_hint = f' — looks like "{quoted[0]}"'

        if count == 1:
            return f"Got your screenshot{error_hint}. Describe what happened or send more screenshots if needed."
        return f"Got {count} screenshots{error_hint}. Describe the issue whenever you're ready."

    except Exception as e:
        logger.error(f"Error handling photo message: {e}")
        return "Something went wrong with that photo — please try again."


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
                return await _run_issue_analysis(
                    issue_description=issue_description,
                    chat_session=chat_session,
                    db=db,
                    image_path=file_path
                )
            except Exception as e:
                logger.error(f"Error analyzing document: {e}", exc_info=True)
                return "Something went wrong analyzing that document — could you describe the issue?"

        else:
            return f"Got the file ({file_name}). What's the issue you're running into?"

    except Exception as e:
        logger.error(f"Error handling document message: {e}")
        return "Something went wrong with that file — please try again."


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


async def _send_telegram_file(
    chat_id: int,
    file_path: str,
    file_name: str,
    mime_type: Optional[str] = None,
) -> bool:
    """Send a file (photo or document) to a Telegram chat.

    Supports both local filesystem paths and HTTP/HTTPS URLs (e.g. Cloudinary).
    """
    import os as _os
    import httpx

    try:
        if not TELEGRAM_API or not TELEGRAM_BOT_TOKEN:
            return False

        is_url = file_path.startswith("http://") or file_path.startswith("https://")
        is_image = (mime_type or "").startswith("image/") or file_path.lower().endswith(
            (".jpg", ".jpeg", ".png", ".gif", ".webp")
        )

        async with httpx.AsyncClient() as client:
            if is_url:
                # Telegram can fetch remote URLs directly — no download needed
                endpoint = "sendPhoto" if is_image else "sendDocument"
                field = "photo" if is_image else "document"
                resp = await client.post(
                    f"{TELEGRAM_API}/{endpoint}",
                    json={"chat_id": chat_id, field: file_path},
                    timeout=30.0,
                )
            else:
                if not _os.path.exists(file_path):
                    logger.warning(f"Attachment not found on disk: {file_path}")
                    return False

                content_type = mime_type or ("image/jpeg" if is_image else "application/octet-stream")
                with open(file_path, "rb") as fh:
                    if is_image:
                        resp = await client.post(
                            f"{TELEGRAM_API}/sendPhoto",
                            data={"chat_id": chat_id},
                            files={"photo": (file_name, fh, content_type)},
                            timeout=30.0,
                        )
                    else:
                        resp = await client.post(
                            f"{TELEGRAM_API}/sendDocument",
                            data={"chat_id": chat_id},
                            files={"document": (file_name, fh, content_type)},
                            timeout=30.0,
                        )

        if resp.status_code != 200:
            logger.error(f"Failed to send attachment {file_name}: {resp.text}")
            return False

        logger.info(f"Sent attachment {file_name} to chat {chat_id}")
        return True

    except Exception as e:
        logger.error(f"Error sending file {file_name}: {e}")
        return False


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
    max_retries: int = 3,
    subject: Optional[str] = None,
    image_path: Optional[str] = None,
    image_paths: Optional[list] = None,
) -> Optional[Dict[str, Any]]:
    """
    Create ticket with retry logic for duplicate ticket_no errors.
    Handles race conditions with database-level locking and exponential backoff.
    """

    import asyncio

    resolved_paths = image_paths or ([image_path] if image_path else [])

    for attempt in range(max_retries):
        try:
            ticket = chat_ticket_service.create_ticket_from_chat(
                chat_session_id=chat_session_id,
                issue_description=issue_description,
                inferred_category=inferred_category,
                subject=subject,
                image_paths=resolved_paths,
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