from fastapi import FastAPI, Request
import requests
import os
import re
from groq import Groq
from dotenv import load_dotenv

from session import get_or_create_session, clear_session
from ticket import create_ticket_from_session
from agent_functions import FUNCTION_MAP, classify_issue_category, _confirm_and_create_ticket
from prompt import GATEKEEPER_PROMPT
from http_routes import http_router

# ------------------ ENV ------------------

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not TELEGRAM_TOKEN:
    raise RuntimeError("Missing TELEGRAM_BOT_TOKEN")

if not GROQ_API_KEY:
    raise RuntimeError("Missing GROQ_API_KEY")

TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
MODEL = "llama-3.1-8b-instant"
UPLOADS_DIR = "uploads"

os.makedirs(UPLOADS_DIR, exist_ok=True)

# ------------------ CLIENT ------------------

client = Groq(api_key=GROQ_API_KEY)

# ------------------ APP ------------------

app = FastAPI()
app.include_router(http_router)

conversation_state: dict[int, list] = {}

# ------------------ TELEGRAM HELPERS ------------------

def send_message(chat_id: int, text: str) -> None:
    if not text or not text.strip():
        return
    try:
        requests.post(
            f"{TELEGRAM_API}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=5
        )
    except Exception as e:
        print(f"Telegram send failed: {e}")


async def download_file(file_id: str, file_name: str) -> str | None:
    try:
        meta = requests.get(
            f"{TELEGRAM_API}/getFile",
            params={"file_id": file_id},
            timeout=5
        ).json()

        if not meta.get("ok"):
            return None

        file_path = meta["result"]["file_path"]
        url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_path}"
        content = requests.get(url, timeout=10)

        if content.status_code == 200:
            local_path = os.path.join(UPLOADS_DIR, file_name)
            with open(local_path, "wb") as f:
                f.write(content.content)
            return local_path

    except Exception as e:
        print(f"File download failed: {e}")

    return None

# ------------------ SILENT DATA EXTRACTION ------------------

async def extract_and_save(chat_id: int, text: str, session) -> None:
    """
    Silently extract and save structured data from user input.
    Does NOT force step progression - just captures what's present.
    """
    t = text.lower().strip()
    
    # Empty message - skip extraction
    if not text or not t:
        return
    
    # Try to detect and save issue description FIRST (longer text, or contains issue keywords)
    if not session.issue_description:
        issue_keywords = ['unable', 'unable to', 'can\'t', 'cannot', 'problem', 'issue', 'error', 'slow', 'blocked', 'crash', 'not working', 'broken']
        has_issue_keyword = any(kw in t for kw in issue_keywords)
        
        if (len(text) > 15) or has_issue_keyword:
            session.issue_description = text
            session.issue_category = classify_issue_category(text)
            return
    
    # Try to extract name and company (look for comma-separated or natural structure)
    if not session.user_name:
        parts = [p.strip() for p in text.split(",")]
        if len(parts) >= 2 and len(parts[0]) > 2 and len(parts[1]) > 2:
            session.user_name = parts[0]
            session.company_name = parts[1]
            return
        # Only take short text as name (2-50 chars), avoid issue descriptions
        if len(text) > 2 and len(text) < 50:
            is_issue = any(kw in t for kw in ['unable', 'problem', 'error', 'slow', 'blocked', 'crash'])
            is_env = any(kw in t for kw in ['prod', 'test', 'local', 'uat'])
            if not is_issue and not is_env:
                session.user_name = text
                return
    
    if not session.company_name and session.user_name and len(text) > 2 and len(text) < 100:
        session.company_name = text
        return
    
    # Try to detect environment
    if not session.environment:
        if "prod" in t:
            session.environment = "Production"
            return
        elif ("uat" in t or "test" in t) and "local" not in t:
            session.environment = "Test / UAT"
            return
        elif "local" in t:
            session.environment = "Local system"
            return
    
    # Try to detect impact level
    if not session.impact:
        if "completely" in t or "fully" in t or "fully blocked" in t:
            session.impact = "Completely blocked"
            return
        elif "partial" in t or "partially" in t:
            session.impact = "Partially blocked"
            return
        elif "slow" in t or "slower" in t or "usable" in t:
            session.impact = "Slow but usable"
            return
    
    # Try to detect software
    if not session.software:
        software_keywords = {
            "teamcenter": "Teamcenter",
            "creo": "Creo",
            "nx": "NX",
            "or-cad": "OR-CAD",
            "autocad": "AutoCAD",
            "fusion": "Fusion 360",
            "solidworks": "SolidWorks",
            "inventor": "Inventor",
        }
        for keyword, name in software_keywords.items():
            if keyword in t:
                session.software = name
                return
        # If not a known keyword but looks like software name, save it
        if len(text) < 50 and not any(c in t for c in ['blocked', 'slow', 'faster', 'production', 'test']):
            session.software = text
            return
        
# ------------------ LLM ------------------

async def run_llm(chat_id: int, user_text: str) -> str:
    session = get_or_create_session(chat_id)
    history = conversation_state.get(chat_id, [])

    # Silent extraction - just capture what's in the message
    await extract_and_save(chat_id, user_text, session)

    # Build missing fields list
    missing = []
    if not session.issue_description:
        missing.append("issue description")
    if not session.user_name:
        missing.append("user name")
    if not session.company_name and session.user_name:
        missing.append("company name")
    if not session.software:
        missing.append("software/system")
    if not session.environment:
        missing.append("environment")
    if not session.impact:
        missing.append("impact level")

    # Check if we have all required info BEFORE building context
    all_collected = all([
        session.user_name,
        session.company_name,
        session.issue_description,
        session.software,
        session.environment,
        session.impact
    ])

    # Check if user is confirming (yes, confirm, create, submit, etc.)
    confirmation_keywords = ['yes', 'confirm', 'create', 'submit', 'proceed', 'ok', 'alright', 'sounds good']
    user_says_yes = any(keyword in user_text.lower() for keyword in confirmation_keywords)

    # Auto-confirm and create ticket if all info present and user confirms
    if all_collected and user_says_yes and not session.ticket_created:
        session.is_confirmed = True
        ticket = create_ticket_from_session(session)
        if ticket:
            session.ticket_created = True
            reply = f"✅ Ticket created successfully! Your ticket ID is: **{ticket.ticket_id}**\n\nOur support team will review this and get back to you shortly."
            send_message(chat_id, reply)
            clear_session(chat_id)
            conversation_state.pop(chat_id, None)
            return reply

    # Build context
    session_context = f"""
Session State:
- User: {session.user_name or 'Not provided'}
- Company: {session.company_name or 'Not provided'}
- Issue: {session.issue_description or 'Not provided'}
- Category: {session.issue_category or 'Not provided'}
- Software: {session.software or 'Not provided'}
- Environment: {session.environment or 'Not provided'}
- Impact: {session.impact or 'Not provided'}
- Files: {len(session.attachments)} attached
- Status: {'Ready for ticket creation - ask for confirmation' if all_collected else 'Collecting information'}

Missing Information (ask for next missing item naturally):
{', '.join(missing) if missing else 'None - ask user to confirm and create ticket'}
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
            max_tokens=250
        )
        reply = (resp.choices[0].message.content or "").strip()
        if not reply:
            reply = "Could you tell me a bit more about what you're experiencing?"

    except Exception as e:
        print(f"LLM error: {e}")
        reply = "Sorry, something went wrong. Please try again."

    conversation_state[chat_id] = (
        history
        + [{"role": "user", "content": user_text}]
        + [{"role": "assistant", "content": reply}]
    )[-10:]

    return reply

# ------------------ WEBHOOK ------------------

@app.post("/telegram/webhook")
async def telegram_webhook(req: Request):
    data = await req.json()
    msg = data.get("message")
    if not msg:
        return {"ok": True}

    chat_id = msg["chat"]["id"]
    session = get_or_create_session(chat_id)

    if "document" in msg:
        path = await download_file(msg["document"]["file_id"], msg["document"]["file_name"])
        if path:
            session.attachments.append(path)
            send_message(chat_id, "Got the file. Please continue.")
        return {"ok": True}

    if "photo" in msg:
        photo = msg["photo"][-1]
        path = await download_file(photo["file_id"], f"screenshot_{chat_id}.jpg")
        if path:
            session.attachments.append(path)
            send_message(chat_id, "Screenshot received. Please continue.")
        return {"ok": True}

    text = msg.get("text", "").strip()
    if not text:
        return {"ok": True}

    reply = await run_llm(chat_id, text)
    send_message(chat_id, reply)

    return {"ok": True}

# ------------------ HEALTH ------------------

@app.get("/health")
async def health():
    from session import sessions
    return {
        "status": "ok",
        "active_sessions": len(sessions)
    }