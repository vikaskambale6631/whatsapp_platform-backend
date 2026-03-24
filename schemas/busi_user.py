from pydantic import BaseModel, EmailStr, Field, ConfigDict
from typing import Optional
from datetime import datetime
import uuid


class BusiUserProfileSchema(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    username: str = Field(..., min_length=3, max_length=100)
    email: EmailStr
    phone: str = Field(..., min_length=10, max_length=20)
    password: str = Field(..., min_length=8, max_length=255)


class BusiUserProfileResponseSchema(BaseModel):
    name: str
    username: str
    email: EmailStr
    phone: str


class BusiUserInfoSchema(BaseModel):
    business_name: str = Field(..., min_length=1, max_length=255)
    business_description: Optional[str] = None
    erp_system: Optional[str] = Field(None, max_length=100)
    gstin: Optional[str] = Field(None, min_length=15, max_length=15)


class BusiUserAddressSchema(BaseModel):
    full_address: Optional[str] = None
    pincode: Optional[str] = Field(None, max_length=10)
    country: Optional[str] = Field(None, max_length=100)


class BusiUserWalletSchema(BaseModel):
    credits_allocated: int = Field(default=0, ge=0)
    credits_used: int = Field(default=0, ge=0)
    credits_remaining: int = Field(default=0, ge=0)


class BusiUserCreateSchema(BaseModel):
    role: str = Field(default="business_owner", max_length=50)
    status: str = Field(default="active", max_length=20)
    parent_reseller_id: uuid.UUID
    profile: BusiUserProfileSchema
    business: BusiUserInfoSchema
    address: Optional[BusiUserAddressSchema] = None
    wallet: Optional[BusiUserWalletSchema] = BusiUserWalletSchema()
    whatsapp_mode: str = Field(default="unofficial", max_length=20)


class BusiUserProfileUpdateSchema(BaseModel):
    name: Optional[str] = None
    username: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    password: Optional[str] = None


class BusiUserUpdateSchema(BaseModel):
    role: Optional[str] = Field(None, max_length=50)
    status: Optional[str] = Field(None, max_length=20)
    profile: Optional[BusiUserProfileUpdateSchema] = None
    business: Optional[BusiUserInfoSchema] = None
    address: Optional[BusiUserAddressSchema] = None
    wallet: Optional[BusiUserWalletSchema] = None
    whatsapp_mode: Optional[str] = Field(None, max_length=20)


class BusiUserResponseSchema(BaseModel):
    busi_user_id: uuid.UUID
    role: str
    status: str
    parent_reseller_id: uuid.UUID
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    profile: BusiUserProfileResponseSchema
    business: BusiUserInfoSchema
    address: Optional[BusiUserAddressSchema] = None
    wallet: BusiUserWalletSchema
    whatsapp_mode: str
    
    # [NEW] Plan and Connection Status
    plan_name: Optional[str] = None
    plan_expiry: Optional[datetime] = None
    connection_status: Optional[str] = "disconnected"

    model_config = ConfigDict(from_attributes=True)


class BusiUserLoginSchema(BaseModel):
    email: EmailStr
    password: str


class BusiUserResponseWithTokenSchema(BaseModel):
    busi_user: BusiUserResponseSchema
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class BusiUserLogoutResponseSchema(BaseModel):
    message: str
    detail: str
    business_type: str = "busi_user"


class BusiUserAnalyticsSchema(BaseModel):
    total_users: int
    active_users: int # For management page (status == active)
    connected_users: int # At least one device connected
    disconnected_users: int
    plan_expired_users: int
    messages_sent: int
