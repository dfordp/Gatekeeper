from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from services.email_service import send_zoho_email

router = APIRouter(prefix="/api/email", tags=["email"])

class EmailSchema(BaseModel):
    to_email: str
    subject: str
    body: str

@router.post("/send-email/")
def api_send_email(email_data: EmailSchema):
    result = send_zoho_email(
        to_email=email_data.to_email,
        subject=email_data.subject,
        body=email_data.body
    )
    if "error" in result:
        raise HTTPException(status_code=500, detail=result['error'])
    return result