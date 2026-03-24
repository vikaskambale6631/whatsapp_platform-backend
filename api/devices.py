from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
import logging

from db.session import get_db
from schemas.device import DeviceResponse as DeviceModelResponse, DeviceCreate, DeviceRegisterRequest, DeviceType, DeviceListResponse
from services.device_service import DeviceService
from models.device import SessionStatus

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Devices"])

def get_device_service(db: Session = Depends(get_db)) -> DeviceService:
    return DeviceService(db)

@router.post("/register", response_model=DeviceModelResponse)
async def register_device(
    request: Request,
    device_service: DeviceService = Depends(get_device_service)
):
    """Register a new device"""
    try:
        # Parse request body manually to handle frontend format
        body = await request.json()
        user_id = body.get("user_id")
        device_name = body.get("device_name")
        device_type = body.get("device_type", "web")
        
        if not user_id or not device_name:
            raise HTTPException(status_code=400, detail="user_id and device_name are required")
        
        # Create device register request
        from uuid import UUID
        
        device_request = DeviceRegisterRequest(
            user_id=UUID(user_id),
            device_name=device_name,
            device_type=DeviceType(device_type.lower())
        )
        
        # Register device using the service
        device = device_service.register_device(UUID(user_id), device_request)
        return device
    except ValueError as e:
        logger.error(f"Validation error registering device: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error registering device: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to register device: {str(e)}")

@router.get("/", response_model=List[DeviceModelResponse])
async def get_devices(
    user_id: str = Query(...),
    session_status: Optional[str] = Query(None),
    device_service: DeviceService = Depends(get_device_service)
):
    """Get all devices for a user, optionally filtered by status"""
    try:
        devices = device_service.get_user_devices(user_id, session_status)
        return devices
    except Exception as e:
        logger.error(f"Error getting devices: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get devices: {str(e)}")

@router.get("/unofficial/connected")
async def get_connected_unofficial_device(
    user_id: str = Query(...),
    device_service: DeviceService = Depends(get_device_service)
):
    """Get the first connected unofficial device for a user"""
    try:
        # Search for devices with 'connected' status only
        devices = device_service.get_user_devices(user_id, session_status="connected")
            
        # Filter for unofficial types only (web, mobile, desktop)
        unofficial_types = ["web", "mobile", "desktop"]
        connected_unofficial = [d for d in devices if d.device_type.value in unofficial_types]
        
        if connected_unofficial:
            # Return list format as expected by frontend's response.data.devices
            device_list = []
            for device in connected_unofficial:
                device_list.append({
                    "device_id": str(device.device_id),
                    "device_name": device.device_name,
                    "session_status": device.session_status.value,
                    "device_type": device.device_type.value
                })
            return {
                "success": True,
                "devices": device_list
            }
        else:
            return {
                "success": False,
                "devices": [],
                "message": "No connected unofficial device found"
            }
    except Exception as e:
        logger.error(f"Error getting connected unofficial device: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{device_id}")
async def get_device(
    device_id: str,
    device_service: DeviceService = Depends(get_device_service)
):
    """Get a specific device by ID"""
    try:
        device = device_service.get_device_by_id(device_id)
        if not device:
            raise HTTPException(status_code=404, detail="Device not found")
        return device
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting device {device_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get device: {str(e)}")

@router.patch("/{device_id}/status")
async def update_device_status(
    device_id: str,
    request: dict,
    device_service: DeviceService = Depends(get_device_service)
):
    """Update device status - called by WhatsApp Engine"""
    try:
        logger.info(f"🔄 Updating device {device_id} status: {request}")
        
        # Extract session_status from request body
        session_status = request.get("session_status", "unknown")
        ip_address = request.get("ip_address")
        
        # Update device status in database
        device = device_service.update_device_status(device_id, session_status, ip_address)
        
        if device:
            logger.info(f"✅ Device {device_id} status updated successfully")
            return {"success": True, "message": "Device status updated"}
        else:
            logger.warning(f"⚠️ Device {device_id} not found - returning 404")
            raise HTTPException(status_code=404, detail="Device not found")
            
    except HTTPException:
        # Re-raise HTTP exceptions (like 404)
        raise
    except Exception as e:
        logger.error(f"Error updating device {device_id} status: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update device status: {str(e)}")

@router.post("/{device_id}/start")
async def start_device_session(
    device_id: str,
    device_service: DeviceService = Depends(get_device_service)
):
    """Start/initialize a WhatsApp session for a device - proxies to WhatsApp Engine"""
    try:
        # Validate device exists in database first
        device = device_service.get_device_by_id(device_id)
        if not device:
            raise HTTPException(status_code=404, detail="Device not found in database")
        
        # Proxy to WhatsApp Engine
        from services.whatsapp_engine_service import WhatsAppEngineService
        engine_service = WhatsAppEngineService(device_service.db)
        result = engine_service.start_session(device_id)
        
        if result.get("success"):
            return {"status": "ok", "message": "Session start initiated", "data": result.get("result")}
        else:
            raise HTTPException(status_code=502, detail=result.get("error", "Failed to start session"))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting session for device {device_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start device session: {str(e)}")

@router.get("/{device_id}/qr")
async def get_device_qr(
    device_id: str,
    device_service: DeviceService = Depends(get_device_service)
):
    """Get QR code for a device - proxies to WhatsApp Engine"""
    try:
        # Validate device exists in database first
        device = device_service.get_device_by_id(device_id)
        if not device:
            raise HTTPException(status_code=404, detail="Device not found in database")
        
        # Proxy to WhatsApp Engine
        from services.whatsapp_engine_service import WhatsAppEngineService
        engine_service = WhatsAppEngineService(device_service.db)
        result = engine_service.get_qr_code(device_id)
        
        if result.get("success"):
            data = result.get("data", {})
            qr_code = data.get("qr_code") or data.get("qr")
            if qr_code:
                return {"qr_code": qr_code, "status": "qr_ready"}
            elif data.get("status") == "connected":
                return {"qr_code": None, "status": "connected"}
            else:
                return {"qr_code": None, "status": data.get("status", "generating")}
        else:
            error = result.get("error", "QR code not available")
            if "ENGINE_NOT_READY" in str(error):
                raise HTTPException(status_code=502, detail=f"ENGINE_NOT_READY: {error}")
            raise HTTPException(status_code=404, detail=error)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting QR for device {device_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get QR code: {str(e)}")

@router.delete("/{device_id}")
async def delete_device(
    device_id: str,
    device_service: DeviceService = Depends(get_device_service)
):
    """Delete/logout a WhatsApp device"""
    try:
        result = device_service.logout_device(device_id)
        
        if result.get("success"):
            return {"message": "Device logged out successfully", "status": result.get("status")}
        else:
            error = result.get("error", "Failed to logout device")
            if error == "device_not_found":
                raise HTTPException(status_code=404, detail="Device not found")
            raise HTTPException(status_code=500, detail=error)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting device {device_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete device: {str(e)}")

@router.get("/official/list", response_model=Dict[str, Any])
async def get_official_devices(
    user_id: str = Query(...),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    device_service: DeviceService = Depends(get_device_service)
):
    """Get official WhatsApp devices for a user with pagination"""
    try:
        devices = device_service.get_devices_by_user_and_type(
            user_id, 
            DeviceType.OFFICIAL, 
            skip=(page - 1) * size, 
            limit=size
        )
        
        # Verify official config health to dynamically determine connection status
        from services.official_whatsapp_config_service import OfficialWhatsAppConfigService
        from models.device import SessionStatus
        config_service = OfficialWhatsAppConfigService(device_service.db)
        config = config_service.get_config_by_user_id(user_id)
        
        is_healthy = False
        if config and config.is_active and config.access_token:
            try:
                # This performs a real API call to Meta to verify token validity
                profile_result = config_service.get_business_profile(config)
                is_healthy = profile_result.success
            except Exception as ex:
                logger.warning(f"Failed to check official config health for user {user_id}: {ex}")
                is_healthy = False

        # Convert to response format
        device_list = []
        for device in devices:
            current_status = device.session_status
            
            # Dynamically push status change to database if it differs
            if is_healthy and current_status != SessionStatus.connected:
                device.session_status = SessionStatus.connected
                device_service.db.commit()
                current_status = SessionStatus.connected
            elif not is_healthy and current_status != SessionStatus.disconnected:
                device.session_status = SessionStatus.disconnected
                device_service.db.commit()
                current_status = SessionStatus.disconnected
                
            device_list.append({
                "device_id": str(device.device_id),
                "busi_user_id": str(device.busi_user_id),
                "device_name": device.device_name,
                "device_type": device.device_type.value,
                "session_status": current_status.value,
                "qr_last_generated": device.qr_last_generated.isoformat() if device.qr_last_generated else None,
                "ip_address": device.ip_address,
                "last_active": device.last_active.isoformat() if device.last_active else None,
                "created_at": device.created_at.isoformat() if device.created_at else None,
                "updated_at": device.updated_at.isoformat() if device.updated_at else None
            })
        
        return {
            "devices": device_list,
            "total": len(device_list),
            "page": page,
            "size": size
        }
    except Exception as e:
        logger.error(f"Error getting official devices: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get official devices: {str(e)}")

@router.get("/unofficial/list", response_model=Dict[str, Any])
async def get_unofficial_devices(
    user_id: str = Query(...),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    device_service: DeviceService = Depends(get_device_service)
):
    """Get unofficial WhatsApp devices for a user with pagination"""
    try:
        # Get all unofficial device types (web, mobile, desktop)
        unofficial_devices = []
        for device_type in [DeviceType.WEB, DeviceType.MOBILE, DeviceType.DESKTOP]:
            devices = device_service.get_devices_by_user_and_type(
                user_id, 
                device_type, 
                skip=(page - 1) * size, 
                limit=size
            )
            unofficial_devices.extend(devices)
        
        # Convert to response format
        device_list = []
        for device in unofficial_devices:
            device_list.append({
                "device_id": str(device.device_id),
                "busi_user_id": str(device.busi_user_id),
                "device_name": device.device_name,
                "device_type": device.device_type.value,
                "session_status": device.session_status.value,
                "qr_last_generated": device.qr_last_generated.isoformat() if device.qr_last_generated else None,
                "ip_address": device.ip_address,
                "last_active": device.last_active.isoformat() if device.last_active else None,
                "created_at": device.created_at.isoformat() if device.created_at else None,
                "updated_at": device.updated_at.isoformat() if device.updated_at else None
            })
        
        return {
            "devices": device_list,
            "total": len(device_list),
            "page": page,
            "size": size
        }
    except Exception as e:
        logger.error(f"Error getting unofficial devices: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get unofficial devices: {str(e)}")