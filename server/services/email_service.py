import requests
import os
from dotenv import load_dotenv
from core.logger import get_logger

# Load environment variables from .env file
load_dotenv()

logger = get_logger(__name__)

# Load Zoho Mail API credentials
ZOHO_ACCOUNT_ID = os.getenv("ZOHO_ACCOUNT_ID")
ZOHO_AUTH_TOKEN = os.getenv("ZOHO_AUTH_TOKEN")
ZOHO_USER = os.getenv("ZOHO_USER")

# Constants
ZOHO_API_BASE_URL = "https://mail.zoho.com/api/accounts"


def send_zoho_email(to_email: str, subject: str, body: str, cc_email: str = None, bcc_email: str = None):
    """
    Sends an email using Zoho Mail's REST API.
    
    Args:
        to_email: Recipient email address
        subject: Email subject
        body: Email content (HTML or plain text)
        cc_email: Optional CC email address
        bcc_email: Optional BCC email address
        
    Returns:
        dict: Response with success or error message
    """
    logger.info(f"Attempting to send email to {to_email} from {ZOHO_USER}")
    
    if not ZOHO_ACCOUNT_ID or not ZOHO_AUTH_TOKEN:
        error_msg = "Zoho API credentials not configured (ZOHO_ACCOUNT_ID or ZOHO_AUTH_TOKEN missing)"
        logger.error(error_msg)
        return {"error": error_msg}
    
    # Prepare request headers
    headers = {
        "Authorization": f"Zoho-oauthtoken {ZOHO_AUTH_TOKEN}",
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    
    # Prepare request body
    payload = {
        "fromAddress": ZOHO_USER,
        "toAddress": to_email,
        "subject": subject,
        "content": body,
        "mailFormat": "html",  # Can be 'html' or 'plaintext'
        "askReceipt": "no"
    }
    
    # Add optional CC and BCC
    if cc_email:
        payload["ccAddress"] = cc_email
    if bcc_email:
        payload["bccAddress"] = bcc_email
    
    # Construct API URL
    url = f"{ZOHO_API_BASE_URL}/{ZOHO_ACCOUNT_ID}/messages"
    
    try:
        logger.info(f"Sending request to {url}")
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        
        # Check response status
        if response.status_code == 200:
            logger.info(f"Email sent successfully to {to_email}")
            return {
                "message": "Email sent successfully!",
                "data": response.json()
            }
        else:
            error_msg = f"Zoho API error: {response.status_code} - {response.text}"
            logger.error(error_msg)
            return {"error": error_msg}
            
    except requests.exceptions.Timeout:
        error_msg = "Request timeout while connecting to Zoho Mail API"
        logger.error(error_msg)
        return {"error": error_msg}
    except requests.exceptions.RequestException as e:
        error_msg = f"Request failed: {e}"
        logger.error(error_msg)
        return {"error": error_msg}
    except Exception as e:
        error_msg = f"Unexpected error: {e}"
        logger.error(error_msg)
        return {"error": error_msg}