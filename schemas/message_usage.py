from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from typing import Optional


class MessageUsageCreditLogBase(BaseModel):
    busi_user_id: str = Field(..., description="UUID of the user (reseller or business)")
    message_id: str = Field(..., description="ID of the message")
    credits_deducted: int = Field(..., description="Number of credits deducted (negative for additions)")
    balance_after: int = Field(..., description="Remaining balance after deduction")


class MessageUsageCreditLogCreate(MessageUsageCreditLogBase):
    timestamp: Optional[datetime] = None


class MessageUsageCreditLogResponse(MessageUsageCreditLogBase):
    usage_id: str
    timestamp: datetime

    model_config = ConfigDict(from_attributes=True)


class MessageUsageCreditLogUpdate(BaseModel):
    credits_deducted: Optional[int] = Field(None)
    balance_after: Optional[int] = Field(None)
