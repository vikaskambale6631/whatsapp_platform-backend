from sqlalchemy import Column, String, DateTime, Integer, Text, Boolean, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from db.base import Base
import uuid


class BusiUser(Base):
    __tablename__ = "businesses"

    busi_user_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    role = Column(String(50), nullable=False, default="business_owner")
    status = Column(String(20), nullable=False, default="active")
    parent_reseller_id = Column(UUID(as_uuid=True), ForeignKey("resellers.reseller_id"), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Profile fields
    name = Column(String(255), nullable=False)
    username = Column(String(100), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    phone = Column(String(20), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)

    # Business fields
    business_name = Column(String(255), nullable=False)
    business_description = Column(Text, nullable=True)
    erp_system = Column(String(100), nullable=True)
    gstin = Column(String(20), unique=True, nullable=True)

    # Address fields
    full_address = Column(Text, nullable=True)
    pincode = Column(String(10), nullable=True)
    country = Column(String(100), nullable=True)

    # Wallet fields (different from User model)
    credits_allocated = Column(Integer, default=0)
    credits_used = Column(Integer, default=0)
    credits_remaining = Column(Integer, default=0)

    # WhatsApp mode
    whatsapp_mode = Column(String(20), default="unofficial")

    # Device limit fields
    max_devices = Column(Integer, default=5)  # Default 5 devices per user
    allow_unlimited_devices = Column(Boolean, default=False)  # Premium unlimited mode

    # Plan fields
    plan_name = Column(String(50), nullable=True)
    plan_expiry = Column(DateTime(timezone=True), nullable=True)

    # Relationship with parent reseller
    parent_reseller = relationship("Reseller", back_populates="business_users")
    
    # 🔥 FIX: Add cascades to prevent NotNullViolation during deletion
    # Relationship with credit distributions received
    credit_distributions_received = relationship(
        "CreditDistribution", 
        back_populates="to_business",
        cascade="all, delete-orphan"
    )

    # Added reference to sheets to ensure they are deleted with the user
    google_sheets = relationship(
        "GoogleSheet",
        back_populates="owner",
        cascade="all, delete-orphan"
    )

    # Relationship with devices
    devices = relationship(
        "Device", 
        primaryjoin="BusiUser.busi_user_id == Device.busi_user_id",
        foreign_keys="[Device.busi_user_id]",
        cascade="all, delete-orphan"
    )

    # Added reference to official whatsapp configurations (if any)
    official_whatsapp_config = relationship(
        "OfficialWhatsAppConfig",
        primaryjoin="BusiUser.busi_user_id == cast(OfficialWhatsAppConfig.busi_user_id, UUID)",
        foreign_keys="[OfficialWhatsAppConfig.busi_user_id]",
        cascade="all, delete-orphan",
        overlaps="official_whatsapp_config"
    )

    # Added reference to contact groups
    contact_groups = relationship(
        "ContactGroup",
        back_populates="user",
        cascade="all, delete-orphan"
    )

    # Added reference to contacts
    contacts = relationship(
        "Contact",
        back_populates="user",
        cascade="all, delete-orphan"
    )

    # Added reference to analytics
    analytics = relationship(
        "BusinessUserAnalytics",
        back_populates="business_user",
        cascade="all, delete-orphan",
        uselist=False
    )

    def __repr__(self):
        return f"<BusiUser(busi_user_id={self.busi_user_id}, username={self.username}, email={self.email})>"
