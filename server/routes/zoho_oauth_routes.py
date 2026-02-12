# server/routes/zoho_oauth_routes.py
"""Zoho OAuth integration routes"""
import os
from fastapi import APIRouter, HTTPException, Query, Request
from urllib.parse import urlencode, parse_qs, urlparse
from pydantic import BaseModel
from typing import Optional
import httpx
from core.config import (
    ZOHO_CLIENT_ID, ZOHO_CLIENT_SECRET, ZOHO_REDIRECT_URI,
    ZOHO_SCOPE, ZOHO_OAUTH_URL, ZOHO_TOKEN_URL, ZOHO_API_BASE_URL
)
from core.logger import get_logger
logger = get_logger(__name__)

router = APIRouter(prefix="/api/zoho", tags=["Zoho OAuth"])

class EmailRequest(BaseModel):
    """Request model for sending emails via Zoho Mail"""
    access_token: str
    account_id: str
    from_address: str
    to_address: str
    subject: str
    content: str
    cc_address: Optional[str] = None
    bcc_address: Optional[str] = None
    mail_format: str = "html"  # html or plaintext
    ask_receipt: str = "no"  # yes or no
    encoding: str = "UTF-8"
    region: Optional[str] = None  # e.g., "in" for India
    
    # Scheduling parameters
    is_schedule: bool = False
    schedule_type: Optional[int] = None  # 1-6
    time_zone: Optional[str] = None
    schedule_time: Optional[str] = None  # MM/DD/YYYY HH:MM:SS


class ScheduledEmailRequest(EmailRequest):
    """Extended model for scheduled emails"""
    is_schedule: bool = True
    schedule_type: int  # 1-6
    time_zone: Optional[str] = None
    schedule_time: Optional[str] = None


@router.get("/oauth/auth")
async def zoho_oauth_authorize():
    """
    Redirect user to Zoho OAuth authorization page.
    
    Returns:
        dict: Authorization URL to redirect to
    """
    if not ZOHO_CLIENT_ID:
        raise HTTPException(
            status_code=500,
            detail="Zoho OAuth not configured - missing ZOHO_CLIENT_ID"
        )
    
    params = {
        "client_id": ZOHO_CLIENT_ID,
        "response_type": "code",
        "scope": ZOHO_SCOPE,
        "redirect_uri": ZOHO_REDIRECT_URI,
        "state": "gatekeeper_oauth_state"
    }
    
    auth_url = f"{ZOHO_OAUTH_URL}?{urlencode(params)}"
    logger.info(f"Generated Zoho OAuth authorization URL")
    
    return {
        "auth_url": auth_url,
        "message": "Redirect to this URL to authorize Zoho access"
    }


@router.get("/oauth/callback")
async def zoho_oauth_callback(
    code: str = Query(...),
    state: str = Query(None),
    location: str = Query(None),
    accounts_server: str = Query(None, alias="accounts-server"),  # Map hyphenated query param to underscore
    request: Request = None
):
    """
    Handle Zoho OAuth callback and exchange authorization code for access token.
    
    Args:
        code: Authorization code from Zoho
        state: State parameter for security verification (optional)
        location: Location/region from Zoho (optional)
        accounts_server: Regional accounts server URL from Zoho (optional, e.g., https://accounts.zoho.in)
        request: FastAPI request object
        
    Returns:
        dict: Access token and user info
    """
    if not code:
        logger.error("OAuth callback missing authorization code")
        raise HTTPException(
            status_code=400,
            detail="Missing authorization code"
        )
    
    # Log the location/region if provided
    if location:
        logger.info(f"Zoho OAuth callback from location: {location}")
    
    # Determine the correct token endpoint based on region
    token_endpoint = ZOHO_TOKEN_URL
    if accounts_server:
        logger.info(f"Received accounts_server: {accounts_server}")
        # accounts_server comes as https://accounts.zoho.in from Zoho
        if accounts_server.startswith("http"):
            token_endpoint = f"{accounts_server.rstrip('/')}/oauth/v2/token"
        else:
            token_endpoint = f"https://{accounts_server}/oauth/v2/token"
        logger.info(f"Using regional token endpoint: {token_endpoint}")
    else:
        logger.info(f"No accounts_server provided, using default: {token_endpoint}")
    
    # State validation is optional since Zoho may not return it
    if state and state != "gatekeeper_oauth_state":
        logger.warning(f"OAuth callback state mismatch - received: {state}")
        raise HTTPException(
            status_code=400,
            detail="Invalid state parameter"
        )
    
    if not ZOHO_CLIENT_ID or not ZOHO_CLIENT_SECRET:
        logger.error("Zoho OAuth credentials not configured")
        raise HTTPException(
            status_code=500,
            detail="Zoho OAuth not properly configured"
        )
    
    try:
        # Exchange authorization code for access token
        token_params = {
            "grant_type": "authorization_code",
            "client_id": ZOHO_CLIENT_ID,
            "client_secret": ZOHO_CLIENT_SECRET,
            "redirect_uri": ZOHO_REDIRECT_URI,
            "code": code
        }
        
        logger.info(f"Exchanging authorization code for access token")
        logger.info(f"Token endpoint: {token_endpoint}")
        logger.info(f"Client ID: {ZOHO_CLIENT_ID[:20]}...")
        
        async with httpx.AsyncClient() as client:
            token_response = await client.post(
                token_endpoint,
                data=token_params,
                timeout=10.0
            )
            
            logger.info(f"Token response status: {token_response.status_code}")
            logger.info(f"Token response body: {token_response.text}")
            
            if token_response.status_code != 200:
                logger.error(f"Token exchange failed with status {token_response.status_code}: {token_response.text}")
                raise HTTPException(
                    status_code=400,
                    detail=f"Token exchange failed: {token_response.text}"
                )
            
            token_data = token_response.json()
            logger.info(f"Zoho token response parsed: {token_data}")
            
            # Check for error in response
            if "error" in token_data:
                logger.error(f"Zoho returned error: {token_data.get('error')}")
                raise HTTPException(
                    status_code=400,
                    detail=f"Zoho OAuth error: {token_data.get('error')}"
                )
            
            access_token = token_data.get("access_token")
            refresh_token = token_data.get("refresh_token")
            expires_in = token_data.get("expires_in")
            
            if not access_token:
                logger.error(f"Token response missing access_token. Full response: {token_data}")
                raise HTTPException(
                    status_code=500,
                    detail="Failed to obtain access token from Zoho"
                )
            
            logger.info(f"Successfully obtained Zoho access token (expires in {expires_in}s)")
            
            # Optionally get user info
            user_info = await get_zoho_user_info(access_token, location)
            
            return {
                "status": "success",
                "access_token": access_token,
                "refresh_token": refresh_token,
                "expires_in": expires_in,
                "user_info": user_info,
                "region": location,
                "message": "Successfully authorized Zoho integration"
            }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"OAuth callback error: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"OAuth callback processing failed: {str(e)}"
        )


async def get_zoho_user_info(access_token: str, region: str = None) -> dict | None:
    """
    Retrieve authenticated user information from Zoho.
    
    Args:
        access_token: Valid Zoho access token
        region: Region/location from Zoho (optional)
        
    Returns:
        dict: User information or None if request fails
    """
    try:
        # Use regional API base URL based on region if provided
        api_base = ZOHO_API_BASE_URL
        if region and region == "in":
            api_base = api_base.replace(".com", ".in")
        
        async with httpx.AsyncClient() as client:
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }
            
            response = await client.get(
                f"{api_base}/users/me",
                headers=headers,
                timeout=5.0
            )
            
            if response.status_code == 200:
                user_data = response.json()
                logger.info(f"Retrieved Zoho user info")
                return user_data
            else:
                logger.warning(f"Failed to retrieve user info: {response.status_code}")
                return None
    
    except Exception as e:
        logger.warning(f"Error retrieving user info: {e}")
        return None


@router.post("/oauth/refresh")
async def refresh_zoho_token(
    refresh_token: str = Query(...),
    region: str = Query(None, description="Region (e.g., 'in' for India)")
):
    """
    Refresh an expired Zoho access token using the refresh token.
    
    According to Zoho docs, the refresh token request should be sent via POST
    with parameters as query parameters or form data.
    
    Args:
        refresh_token: Valid refresh token from previous authorization
        region: Optional region code (e.g., 'in' for India) to use regional endpoint
        
    Returns:
        dict: New access token and expires_in
    """
    if not refresh_token:
        raise HTTPException(
            status_code=400,
            detail="Missing refresh_token"
        )
    
    if not ZOHO_CLIENT_ID or not ZOHO_CLIENT_SECRET:
        logger.error("Zoho OAuth credentials not configured")
        raise HTTPException(
            status_code=500,
            detail="Zoho OAuth not properly configured"
        )
    
    # Determine the correct token endpoint based on region
    token_endpoint = ZOHO_TOKEN_URL
    if region:
        # Map region codes to Zoho domains
        region_map = {
            "in": "https://accounts.zoho.in/oauth/v2/token",
            "com": "https://accounts.zoho.com/oauth/v2/token",
            "eu": "https://accounts.zoho.eu/oauth/v2/token",
            "au": "https://accounts.zoho.com.au/oauth/v2/token"
        }
        token_endpoint = region_map.get(region.lower(), ZOHO_TOKEN_URL)
        logger.info(f"Using regional token endpoint for region '{region}': {token_endpoint}")
    
    try:
        # Build the request parameters as per Zoho documentation
        refresh_params = {
            "grant_type": "refresh_token",
            "client_id": ZOHO_CLIENT_ID,
            "client_secret": ZOHO_CLIENT_SECRET,
            "refresh_token": refresh_token
        }
        
        logger.info(f"Requesting token refresh from: {token_endpoint}")
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                token_endpoint,
                data=refresh_params,
                timeout=10.0
            )
            
            logger.info(f"Token refresh response status: {response.status_code}")
            logger.info(f"Token refresh response body: {response.text}")
            
            if response.status_code != 200:
                logger.error(f"Token refresh failed with status {response.status_code}: {response.text}")
                raise HTTPException(
                    status_code=400,
                    detail=f"Failed to refresh access token: {response.text}"
                )
            
            token_data = response.json()
            
            # Check for error in response
            if "error" in token_data:
                logger.error(f"Zoho returned error during refresh: {token_data.get('error')}")
                raise HTTPException(
                    status_code=400,
                    detail=f"Zoho OAuth error: {token_data.get('error')}"
                )
            
            access_token = token_data.get("access_token")
            if not access_token:
                logger.error(f"Refresh response missing access_token: {token_data}")
                raise HTTPException(
                    status_code=500,
                    detail="Failed to obtain new access token"
                )
            
            logger.info(f"Successfully refreshed Zoho access token (expires in {token_data.get('expires_in')}s)")
            
            return {
                "status": "success",
                "access_token": access_token,
                "expires_in": token_data.get("expires_in"),
                "token_type": token_data.get("token_type", "Bearer"),
                "api_domain": token_data.get("api_domain"),
                "message": "Access token refreshed successfully"
            }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Token refresh error: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Token refresh failed"
        )


@router.post("/oauth/revoke")
async def revoke_zoho_token(
    token: str = Query(..., description="Refresh token to revoke"),
    region: str = Query(None, description="Region (e.g., 'in' for India)")
):
    """
    Revoke a Zoho refresh token to invalidate it.
    
    According to Zoho docs: POST to oauth/v2/token/revoke with token parameter
    
    Args:
        token: Refresh token to revoke
        region: Optional region code (e.g., 'in' for India) to use regional endpoint
        
    Returns:
        dict: Revocation status
    """
    if not token:
        raise HTTPException(
            status_code=400,
            detail="Missing token to revoke"
        )
    
    # Determine the correct revoke endpoint based on region
    revoke_endpoint = ZOHO_TOKEN_URL.replace("/token", "/token/revoke")
    if region:
        # Map region codes to Zoho domains
        region_map = {
            "in": "https://accounts.zoho.in/oauth/v2/token/revoke",
            "com": "https://accounts.zoho.com/oauth/v2/token/revoke",
            "eu": "https://accounts.zoho.eu/oauth/v2/token/revoke",
            "au": "https://accounts.zoho.com.au/oauth/v2/token/revoke"
        }
        revoke_endpoint = region_map.get(region.lower(), revoke_endpoint)
        logger.info(f"Using regional revoke endpoint for region '{region}': {revoke_endpoint}")
    
    try:
        logger.info(f"Revoking token at: {revoke_endpoint}")
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                revoke_endpoint,
                params={"token": token},
                timeout=10.0
            )
            
            logger.info(f"Token revoke response status: {response.status_code}")
            logger.info(f"Token revoke response body: {response.text}")
            
            # Zoho returns 200 on successful revocation
            if response.status_code == 200:
                logger.info("Successfully revoked refresh token")
                return {
                    "status": "success",
                    "message": "Refresh token revoked successfully"
                }
            else:
                logger.error(f"Token revocation failed with status {response.status_code}: {response.text}")
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Failed to revoke token: {response.text}"
                )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Token revocation error: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Token revocation failed"
        )

@router.post("/mail/send")
async def send_email(req: EmailRequest):
    """
    Send an email using Zoho Mail API.
    
    Requires ZohoMail.messages.CREATE or ZohoMail.messages.ALL scope.
    
    Args:
        req: EmailRequest containing email details
        
    Returns:
        dict: Email send status and message ID
    """
    if not req.access_token:
        raise HTTPException(
            status_code=400,
            detail="Missing access_token"
        )
    
    if not req.account_id:
        raise HTTPException(
            status_code=400,
            detail="Missing account_id"
        )
    
    # Validate email addresses
    if not req.from_address or not req.to_address:
        raise HTTPException(
            status_code=400,
            detail="Missing from_address or to_address"
        )
    
    # Determine the mail API base URL based on region
    mail_api_url = "https://mail.zoho.com"
    if req.region:
        region_map = {
            "in": "https://mail.zoho.in",
            "eu": "https://mail.zoho.eu",
            "au": "https://mail.zoho.com.au"
        }
        mail_api_url = region_map.get(req.region.lower(), "https://mail.zoho.com")
        logger.info(f"Using regional mail API: {mail_api_url}")
    
    # Build request URL
    endpoint_url = f"{mail_api_url}/api/accounts/{req.account_id}/messages"
    
    # Build request body
    email_payload = {
        "fromAddress": req.from_address,
        "toAddress": req.to_address,
        "subject": req.subject,
        "content": req.content,
        "mailFormat": req.mail_format,
        "askReceipt": req.ask_receipt,
        "encoding": req.encoding
    }
    
    # Add optional fields
    if req.cc_address:
        email_payload["ccAddress"] = req.cc_address
    
    if req.bcc_address:
        email_payload["bccAddress"] = req.bcc_address
    
    # Add scheduling parameters if scheduled
    if req.is_schedule:
        if not req.schedule_type or req.schedule_type < 1 or req.schedule_type > 6:
            raise HTTPException(
                status_code=400,
                detail="Invalid schedule_type. Must be between 1 and 6."
            )
        
        email_payload["isSchedule"] = "true"
        email_payload["scheduleType"] = req.schedule_type
        
        if req.schedule_type == 6:
            # Custom scheduling requires timezone and scheduleTime
            if not req.time_zone or not req.schedule_time:
                raise HTTPException(
                    status_code=400,
                    detail="For custom scheduling (scheduleType=6), both timeZone and scheduleTime are required."
                )
            email_payload["timeZone"] = req.time_zone
            email_payload["scheduleTime"] = req.schedule_time
        else:
            email_payload["isSchedule"] = "true"    
    try:
        logger.info(f"Sending email to {req.to_address} from {req.from_address}")
        logger.info(f"Email endpoint: {endpoint_url}")
        
        async with httpx.AsyncClient() as client:
            # Try different authentication methods
            auth_attempts = [
                {
                    "name": "Authorization header (Bearer)",
                    "headers": {"Authorization": f"Bearer {req.access_token}", "Content-Type": "application/json"}
                },
                {
                    "name": "Authorization header (Zoho-oauthtoken)",
                    "headers": {"Authorization": f"Zoho-oauthtoken {req.access_token}", "Content-Type": "application/json"}
                },
                {
                    "name": "X-com-zoho-mail-token header",
                    "headers": {"X-com-zoho-mail-token": req.access_token, "Content-Type": "application/json"}
                },
            ]
            
            response = None
            successful_method = None
            
            for attempt in auth_attempts:
                logger.info(f"Trying authentication method: {attempt['name']}")
                try:
                    response = await client.post(
                        endpoint_url,
                        json=email_payload,
                        headers=attempt["headers"],
                        timeout=30.0
                    )
                    logger.info(f"Response status: {response.status_code}")
                    logger.info(f"Response body: {response.text}")
                    
                    if response.status_code == 200:
                        successful_method = attempt['name']
                        logger.info(f"Success with method: {successful_method}")
                        break
                    elif response.status_code != 401:
                        # If it's not a 401, this might be a real error, so break
                        break
                except Exception as e:
                    logger.warning(f"Authentication attempt failed: {e}")
                    continue
            
            if response and response.status_code == 200:
                response_data = response.json()
                message_id = response_data.get("data", {}).get("messageId")
                logger.info(f"Email sent successfully using {successful_method}. Message ID: {message_id}")
                
                return {
                    "status": "success",
                    "message_id": message_id,
                    "recipient": req.to_address,
                    "scheduled": req.is_schedule,
                    "schedule_type": req.schedule_type if req.is_schedule else None,
                    "message": "Email sent successfully" if not req.is_schedule else "Email scheduled successfully"
                }
            elif response and response.status_code == 401:
                logger.error("All authentication methods returned 401")
                raise HTTPException(
                    status_code=401,
                    detail="Unauthorized - Invalid or expired access token. Ensure the OAuth token has ZohoMail.messages.ALL and ZohoMail.accounts.READ scopes."
                )
            elif response and response.status_code == 400:
                response_data = response.json()
                error_message = response_data.get("data", {}).get("moreInfo", response.text)
                logger.error(f"Email send failed: {error_message}")
                raise HTTPException(
                    status_code=400,
                    detail=f"Email send failed: {error_message}"
                )
            else:
                error_detail = response.text if response else "Unknown error"
                error_status = response.status_code if response else 500
                logger.error(f"Email send failed: {error_detail}")
                raise HTTPException(
                    status_code=error_status,
                    detail=f"Email send failed: {error_detail}"
                )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Email send error: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Email send failed"
        )


@router.post("/mail/send-scheduled")
async def send_scheduled_email(req: ScheduledEmailRequest):
    """
    Send a scheduled email using Zoho Mail API.
    
    This is a convenience endpoint for scheduled emails.
    
    Args:
        req: ScheduledEmailRequest containing email and scheduling details
        
    Returns:
        dict: Email scheduling status and schedule ID
    """
    # Use the main send_email logic
    return await send_email(req)


@router.get("/mail/accounts")
async def get_mail_accounts(
    access_token: str = Query(...),
    region: str = Query(None)
):
    """
    Get all Zoho Mail accounts for the authenticated user.
    
    Required to retrieve the accountId needed for sending emails.
    
    Args:
        access_token: Valid Zoho access token
        region: Optional region code (e.g., 'in' for India)
        
    Returns:
        dict: List of mail accounts with their IDs and email addresses
    """
    if not access_token:
        raise HTTPException(
            status_code=400,
            detail="Missing access_token"
        )
    
    # Determine the mail API base URL based on region
    mail_api_url = "https://mail.zoho.com"
    if region:
        region_map = {
            "in": "https://mail.zoho.in",
            "eu": "https://mail.zoho.eu",
            "au": "https://mail.zoho.com.au"
        }
        mail_api_url = region_map.get(region.lower(), "https://mail.zoho.com")
        logger.info(f"Using regional mail API: {mail_api_url}")
    
    endpoint_url = f"{mail_api_url}/api/accounts"
    
    try:
        logger.info(f"Fetching Zoho Mail accounts from: {endpoint_url}")
        
        async with httpx.AsyncClient() as client:
            # Try different authentication methods
            auth_attempts = [
                {
                    "name": "Authorization header (Bearer)",
                    "headers": {"Authorization": f"Bearer {access_token}"},
                    "params": {}
                },
                {
                    "name": "Authorization header (Zoho-oauthtoken)",
                    "headers": {"Authorization": f"Zoho-oauthtoken {access_token}"},
                    "params": {}
                },
                {
                    "name": "X-com-zoho-mail-token header",
                    "headers": {"X-com-zoho-mail-token": access_token},
                    "params": {}
                },
            ]
            
            response = None
            successful_method = None
            
            for attempt in auth_attempts:
                logger.info(f"Trying authentication method: {attempt['name']}")
                try:
                    response = await client.get(
                        endpoint_url,
                        headers=attempt["headers"],
                        params=attempt["params"],
                        timeout=10.0
                    )
                    logger.info(f"Response status: {response.status_code}, body: {response.text}")
                    
                    if response.status_code == 200:
                        successful_method = attempt['name']
                        logger.info(f"Success with method: {successful_method}")
                        break
                    elif response.status_code != 401:
                        # If it's not a 401, this might be a real error, so break
                        break
                except Exception as e:
                    logger.warning(f"Authentication attempt failed: {e}")
                    continue
            
            if response and response.status_code == 200:
                response_data = response.json()
                accounts = response_data.get("data", [])
                logger.info(f"Retrieved {len(accounts)} mail account(s) using method: {successful_method}")
                
                return {
                    "status": "success",
                    "accounts": accounts,
                    "message": f"Retrieved {len(accounts)} account(s)"
                }
            elif response and response.status_code == 401:
                logger.error("All authentication methods returned 401")
                raise HTTPException(
                    status_code=401,
                    detail="Unauthorized - Invalid or expired access token. Ensure the OAuth token has ZohoMail.messages.ALL and ZohoMail.accounts.READ scopes."
                )
            else:
                error_detail = response.text if response else "Unknown error"
                logger.error(f"Failed to fetch accounts: {error_detail}")
                raise HTTPException(
                    status_code=response.status_code if response else 500,
                    detail=f"Failed to fetch mail accounts: {error_detail}"
                )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Mail accounts fetch error: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to fetch mail accounts"
        )