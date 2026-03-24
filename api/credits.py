from fastapi import APIRouter, Depends, HTTPException, status, Header, Query, Request
from pydantic import BaseModel, Field
from fastapi import Header, Query, Request
import logging

logger = logging.getLogger(__name__)
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timedelta
from models.busi_user import BusiUser
from models.reseller import Reseller
from schemas.message_usage import MessageUsageCreditLogResponse
from services.message_usage_service import MessageUsageService
from services.payment_service import PaymentService
from services.audit_log_service import AuditLogService
from schemas.audit_log import AuditLogCreate
from models.payment_order import PaymentOrder
from core.config import settings
from core.security import get_current_user_id
from db.session import get_db
import uuid

router = APIRouter(tags=["Credits"])

@router.get("/balance")
async def get_my_balance(
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    Get current credit balance.
    Fetches directly from the User or Reseller wallet tables.
    """
    # Try BusiUser first (most common)
    user = db.query(BusiUser).filter(BusiUser.busi_user_id == user_id).first()
    if user:
        return {
            "user_id": str(user.busi_user_id),
            "user_type": "business",
            "current_balance": max(0, user.credits_remaining or 0),
            "credits_used": max(0, user.credits_used or 0)
        }
    
    # Try Reseller
    reseller = db.query(Reseller).filter(Reseller.reseller_id == user_id).first()
    if reseller:
         return {
            "user_id": str(reseller.reseller_id),
            "user_type": "reseller",
            "current_balance": max(0, reseller.available_credits or 0),
            "credits_used": max(0, reseller.used_credits or 0)
        }

    raise HTTPException(status_code=404, detail="User wallet not found")

@router.get("/summary")
async def get_my_credit_summary(
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    Get credit summary (Total usage, latest deduction details).
    """
    service = MessageUsageService(db)
    return service.get_credit_summary(user_id)

from pydantic import BaseModel
from datetime import timedelta

class PlanPurchaseRequest(BaseModel):
    plan_name: str
    credits: int
    price: float
    allocated_to_user_id: Optional[str] = None  # busi_user_id to allocate credits to (reseller buying for busi_user)

@router.post("/purchase-plan")
async def purchase_plan(
    request: PlanPurchaseRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    Purchase a credit plan and update the user's wallet.
    """
    try:
        # Try BusiUser first
        user = db.query(BusiUser).filter(BusiUser.busi_user_id == user_id).first()
        if user:
            user.credits_remaining = (user.credits_remaining or 0) + request.credits
            user.credits_allocated = (user.credits_allocated or 0) + request.credits
            user.plan_name = request.plan_name
            user.plan_expiry = datetime.now() + timedelta(days=365)
            
            # Create usage log for purchase
            from models.message_usage import MessageUsageCreditLog
            purchase_log = MessageUsageCreditLog(
                usage_id=f"purchase-{uuid.uuid4().hex[:8]}",
                busi_user_id=str(user.busi_user_id),
                message_id=f"PLAN-{request.plan_name}",
                credits_deducted=-request.credits, # Negative = Added
                balance_after=user.credits_remaining,
                timestamp=datetime.now()
            )
            db.add(purchase_log)
            
            # Audit Log
            audit_service = AuditLogService(db)
            audit_log = AuditLogCreate(
                reseller_id=user.parent_reseller_id if hasattr(user, 'parent_reseller_id') else None,
                performed_by_id=user.busi_user_id,
                performed_by_name=user.business_name or user.name,
                performed_by_role="business",
                affected_user_id=user.busi_user_id,
                affected_user_name=user.business_name or user.name,
                affected_user_email=user.email,
                action_type="PLAN PURCHASE",
                module="Credits",
                description=f"Purchased {request.plan_name} plan (+{request.credits} credits)",
                changes_made=[f"plan: {request.plan_name}", f"credits: +{request.credits}"]
            )
            audit_service.create_log(audit_log)

            db.commit()
            db.refresh(user)
            
            return {
                "success": True,
                "message": f"Successfully purchased {request.plan_name} plan",
                "new_balance": user.credits_remaining,
                "expiry": user.plan_expiry
            }
        
        # Try Reseller
        reseller = db.query(Reseller).filter(Reseller.reseller_id == user_id).first()
        if reseller:
            reseller.available_credits = (reseller.available_credits or 0) + request.credits
            reseller.total_credits = (reseller.total_credits or 0) + request.credits
            
            # Create usage log for purchase
            from models.message_usage import MessageUsageCreditLog
            purchase_log = MessageUsageCreditLog(
                usage_id=f"purchase-{uuid.uuid4().hex[:8]}",
                busi_user_id=str(reseller.reseller_id),
                message_id=f"PLAN-{request.plan_name}",
                credits_deducted=-request.credits, # Negative = Added
                balance_after=reseller.available_credits,
                timestamp=datetime.now()
            )
            db.add(purchase_log)
            
            # Audit Log
            audit_service = AuditLogService(db)
            audit_log = AuditLogCreate(
                reseller_id=reseller.reseller_id,
                performed_by_id=reseller.reseller_id,
                performed_by_name=reseller.name or "Reseller",
                performed_by_role="reseller",
                affected_user_id=reseller.reseller_id,
                affected_user_name=reseller.name or "Reseller",
                affected_user_email=reseller.email,
                action_type="PLAN PURCHASE",
                module="Credits",
                description=f"Purchased {request.plan_name} plan (+{request.credits} credits)",
                changes_made=[f"plan: {request.plan_name}", f"credits: +{request.credits}"]
            )
            audit_service.create_log(audit_log)

            db.commit()
            db.refresh(reseller)
            
            return {
                "success": True,
                "message": f"Successfully purchased {request.plan_name} plan",
                "new_balance": reseller.available_credits,
                "expiry": None
            }
        
        # User not found
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to purchase plan: {str(e)}"
        )

@router.post("/initiate-payment")
async def initiate_payment(
    request: PlanPurchaseRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    Step 1: Create a Razorpay order.
    """
    # 1. Verify User
    user = db.query(BusiUser).filter(BusiUser.busi_user_id == user_id).first()
    user_type = "business"
    if not user:
        user = db.query(Reseller).filter(Reseller.reseller_id == user_id).first()
        user_type = "reseller"
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # 2. Setup Order Data
    txnid = f"OD-{uuid.uuid4().hex[:12].upper()}"
    
    # Calculate amount with GST (18%)
    gst_rate = 0.18
    raw_amount = float(request.price) * (1 + gst_rate)
    
    # 3. Create Order via Razorpay
    payment_service = PaymentService()
    notes = {
        "user_id": str(user_id),
        "user_type": user_type,
        "plan_name": request.plan_name,
        "credits": str(request.credits),
        "txnid": txnid
    }
    
    result = payment_service.create_order(
        amount=raw_amount,
        notes=notes
    )
    
    if result.get("success"):
        razor_order = result["order"]
        # 4. Create Payment Order in DB
        new_order = PaymentOrder(
            txnid=txnid,
            razorpay_order_id=razor_order["id"],
            user_id=user_id,
            user_type=user_type,
            plan_name=request.plan_name,
            credits=request.credits,
            amount=raw_amount,
            status="pending",
            allocated_to_user_id=uuid.UUID(request.allocated_to_user_id) if request.allocated_to_user_id else None,
            is_allocated="pending"
        )
        db.add(new_order)
        db.commit()
        
        return {
            "success": True, 
            "razorpay_order_id": razor_order["id"],
            "amount": razor_order["amount"],
            "currency": razor_order["currency"],
            "key": settings.RAZORPAY_KEY_ID,
            "txnid": txnid
        }
    else:
        error_detail = result.get("error", "Unknown Razorpay error")
        logger.error(f"Razorpay order creation failed for {user_id}: {error_detail}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail=f"Payment Gateway Error: {error_detail}"
        )

class RazorpayCallback(BaseModel):
    razorpay_payment_id: str
    razorpay_order_id: str
    razorpay_signature: str

@router.post("/payment-callback")
async def payment_callback(
    callback: RazorpayCallback,
    db: Session = Depends(get_db)
):
    """
    Step 2: Verify Razorpay signature and update credits.
    """
    # 1. Verify Signature
    payment_service = PaymentService()
    if not payment_service.verify_signature(
        razorpay_order_id=callback.razorpay_order_id,
        razorpay_payment_id=callback.razorpay_payment_id,
        razorpay_signature=callback.razorpay_signature
    ):
        logger.error(f"Invalid Razorpay signature for order: {callback.razorpay_order_id}")
        raise HTTPException(status_code=400, detail="Invalid payment signature")

    # 2. Find Order
    order = db.query(PaymentOrder).filter(PaymentOrder.razorpay_order_id == callback.razorpay_order_id).first()
    if not order:
        logger.error(f"Order not found for Razorpay order ID: {callback.razorpay_order_id}")
        raise HTTPException(status_code=404, detail="Order not found")

    if order.status == "success":
        return {"success": True, "message": "Credits already updated"}

    # 3. Update Order and Credits
    order.status = "success"
    order.razorpay_payment_id = callback.razorpay_payment_id
    order.razorpay_signature = callback.razorpay_signature
    
    # 4. Check if we need to auto-allocate to a specific business user
    is_auto_allocated = bool(order.allocated_to_user_id and order.is_allocated == "pending")

    if not is_auto_allocated:
        # Add credits directly to the purchaser's wallet
        if order.user_type == "business":
            user = db.query(BusiUser).filter(BusiUser.busi_user_id == order.user_id).first()
            if user:
                user.credits_remaining = (user.credits_remaining or 0) + order.credits
                user.credits_allocated = (user.credits_allocated or 0) + order.credits
                user.plan_name = order.plan_name
                user.plan_expiry = datetime.now() + timedelta(days=365)
                current_balance = user.credits_remaining
        else:
            reseller = db.query(Reseller).filter(Reseller.reseller_id == order.user_id).first()
            if reseller:
                reseller.available_credits = (reseller.available_credits or 0) + order.credits
                reseller.total_credits = (reseller.total_credits or 0) + order.credits
                current_balance = reseller.available_credits
        
        # Create usage log for the purchaser
        from models.message_usage import MessageUsageCreditLog
        payment_log = MessageUsageCreditLog(
            usage_id=f"pay-{uuid.uuid4().hex[:8]}",
            busi_user_id=order.user_id,
            message_id=f"RAZORPAY-{order.razorpay_payment_id}",
            credits_deducted=-order.credits, # Negative = Added
            balance_after=current_balance,
            timestamp=datetime.now()
        )
        db.add(payment_log)
    else:
        # 5. Auto-allocate credits DIRECTLY to the business user (skip adding to reseller)
        busi_user = db.query(BusiUser).filter(BusiUser.busi_user_id == order.allocated_to_user_id).first()
        if busi_user:
            busi_user.credits_remaining = (busi_user.credits_remaining or 0) + order.credits
            busi_user.credits_allocated = (busi_user.credits_allocated or 0) + order.credits
            busi_user.plan_name = order.plan_name
            busi_user.plan_expiry = datetime.now() + timedelta(days=365)
            
            # Log the allocation to business user wallet
            from models.message_usage import MessageUsageCreditLog
            busi_log = MessageUsageCreditLog(
                usage_id=f"alloc-{uuid.uuid4().hex[:8]}",
                busi_user_id=str(busi_user.busi_user_id),
                message_id=f"PLAN-ALLOC-{order.plan_name}-{callback.razorpay_payment_id}",
                credits_deducted=-order.credits,  # Negative = Added
                balance_after=busi_user.credits_remaining,
                timestamp=datetime.now()
            )
            db.add(busi_log)
            order.is_allocated = "allocated"
            logger.info(f"Auto-allocated {order.credits} credits to busi_user {order.allocated_to_user_id}")
    
    db.commit()
    return {"success": True, "message": "Credits updated successfully"}


class AllocateCreditsRequest(BaseModel):
    order_txnid: str
    busi_user_id: str

@router.post("/allocate-to-user")
async def allocate_credits_to_user(
    request: AllocateCreditsRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    Manually allocate credits from a paid order to a specific business user.
    Only the reseller who purchased the order can allocate it.
    """
    # Find the order
    order = db.query(PaymentOrder).filter(PaymentOrder.txnid == request.order_txnid).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    # Check ownership - must be the one who bought
    if str(order.user_id) != str(user_id):
        raise HTTPException(status_code=403, detail="You can only allocate your own orders")
    
    # Check order is paid
    if order.status != "success":
        raise HTTPException(status_code=400, detail="Order must be paid (status=success) before allocation")
    
    # Check not already allocated
    if order.is_allocated == "allocated":
        raise HTTPException(status_code=400, detail="Credits already allocated from this order")
    
    # Find the target business user
    busi_user = db.query(BusiUser).filter(BusiUser.busi_user_id == request.busi_user_id).first()
    if not busi_user:
        raise HTTPException(status_code=404, detail="Business user not found")
    
    try:
        # Allocate credits
        busi_user.credits_remaining = (busi_user.credits_remaining or 0) + order.credits
        busi_user.credits_allocated = (busi_user.credits_allocated or 0) + order.credits
        busi_user.plan_name = order.plan_name
        busi_user.plan_expiry = datetime.now() + timedelta(days=365)
        
        # If reseller, deduct from reseller's available_credits
        reseller = db.query(Reseller).filter(Reseller.reseller_id == user_id).first()
        if reseller and order.user_type == "reseller":
            if reseller.available_credits < order.credits:
                raise HTTPException(status_code=400, detail=f"Insufficient reseller credits. Available: {reseller.available_credits}")
            reseller.available_credits -= order.credits
            reseller.used_credits = (reseller.used_credits or 0) + order.credits
        
        # Log for busi_user (addition)
        from models.message_usage import MessageUsageCreditLog
        busi_log = MessageUsageCreditLog(
            usage_id=f"alloc-{uuid.uuid4().hex[:8]}",
            busi_user_id=str(busi_user.busi_user_id),
            message_id=f"PLAN-ALLOC-{order.plan_name}",
            credits_deducted=-order.credits,  # Negative = Added
            balance_after=busi_user.credits_remaining,
            timestamp=datetime.now()
        )
        db.add(busi_log)
        
        # Mark order as allocated
        order.is_allocated = "allocated"
        order.allocated_to_user_id = uuid.UUID(request.busi_user_id)
        
        # Audit Log
        audit_service = AuditLogService(db)
        audit_log = AuditLogCreate(
            reseller_id=uuid.UUID(user_id),
            performed_by_id=uuid.UUID(user_id),
            performed_by_name=reseller.name if reseller else "Reseller",
            performed_by_role="reseller",
            affected_user_id=busi_user.busi_user_id,
            affected_user_name=busi_user.business_name or busi_user.name,
            affected_user_email=busi_user.email,
            action_type="CREDIT ALLOCATION",
            module="Credits",
            description=f"Manually allocated {order.credits} credits from order {order.txnid}",
            changes_made=[f"credits_allocated: +{order.credits}", f"plan: {order.plan_name}"]
        )
        audit_service.create_log(audit_log)
        
        db.commit()
        
        return {
            "success": True,
            "message": f"Successfully allocated {order.credits} credits to business user",
            "busi_user_id": request.busi_user_id,
            "credits_allocated": order.credits,
            "new_balance": busi_user.credits_remaining
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error allocating credits: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to allocate credits: {str(e)}")


@router.get("/usage", response_model=List[MessageUsageCreditLogResponse])
async def get_my_usage_history(
    user_id: str = Depends(get_current_user_id),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    db: Session = Depends(get_db)
):
    """
    Get message usage/credit history.
    """
    service = MessageUsageService(db)
    return service.get_user_usage_logs(
        busi_user_id=user_id,
        skip=skip,
        limit=limit,
        start_date=start_date,
        end_date=end_date
    )

@router.get("/orders", response_model=List[dict])
async def get_my_orders(
    user_id: str = Depends(get_current_user_id),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db)
):
    """
    Get user's payment orders history.
    """
    orders = db.query(PaymentOrder).filter(
        PaymentOrder.user_id == user_id
    ).order_by(
        PaymentOrder.created_at.desc()
    ).offset(skip).limit(limit).all()
    
    # Convert to dict for JSON response
    return [
        {
            "id": str(order.id),
            "txnid": order.txnid,
            "plan_name": order.plan_name,
            "credits": order.credits,
            "amount": order.amount,
            "status": order.status,
            "razorpay_order_id": order.razorpay_order_id,
            "razorpay_payment_id": order.razorpay_payment_id,
            "allocated_to_user_id": str(order.allocated_to_user_id) if order.allocated_to_user_id else None,
            "is_allocated": order.is_allocated or "pending",
            "created_at": order.created_at.isoformat() if order.created_at else None,
            "updated_at": order.updated_at.isoformat() if order.updated_at else None
        }
        for order in orders
    ]
