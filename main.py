from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from datetime import datetime
from db.base import engine, Base
from db.session import get_db
from sqlalchemy import text
from fastapi import Depends
from db.init_db import init_db
# Import all models to ensure they're registered with Base.metadata
from models import *
from api import (
    reseller_router, business_router, credit_distribution_router,
    devices_router, device_sessions_router, message_usage_router,
    reseller_analytics_router, official_whatsapp_config_router,
    whatsapp_router, user_router, auth_router, google_sheets_router,
    replies_router, token_validation_router, webhooks_router,
    campaigns_router, audit_logs_router, groups_router,
    quick_replies_router, unofficial_public_api_router,
    official_public_api_router, credits_router
)

import uvicorn
import asyncio
import logging
from core.config import settings

class CategoryFilter(logging.Filter):
    """
    🔥 CUSTOM LOGGING FILTER
    Injects default category if missing to prevent KeyError/ValueError
    Makes category OPTIONAL, not mandatory
    """
    def filter(self, record):
        # Set default category if not provided
        if not hasattr(record, 'category'):
            # Use logger name as default category, fallback to GENERAL
            record.category = getattr(record, 'name', 'GENERAL').split('.')[-1].upper()
        
        # Ensure category is always a string
        if record.category and not isinstance(record.category, str):
            record.category = str(record.category)
        
        return True

# Configure structured logging with categories - ROBUST VERSION
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - [%(category)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# 🔥 Apply category filter to ALL handlers to handle ALL loggers
category_filter = CategoryFilter()
for handler in logging.root.handlers:
    handler.addFilter(category_filter)

# Create category-specific loggers
db_logger = logging.getLogger("MAIN")

# Force reload
device_logger = logging.getLogger('DEVICE') 
sync_logger = logging.getLogger('SYNC')
engine_logger = logging.getLogger('ENGINE')
qr_logger = logging.getLogger('QR')
session_logger = logging.getLogger('SESSION')

# Reduce noise from third-party libraries
logging.getLogger('requests').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)
logging.getLogger('sqlalchemy').setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

# Global background task references
background_tasks = []

async def keep_engine_alive():
    """🔥 [KEEP-ALIVE] Pings the WhatsApp Engine every 10 minutes to prevent Render Free Tier sleep"""
    from services.whatsapp_engine_service import WhatsAppEngineService
    # We create a local instance to avoid circular imports if any, though here it's fine
    engine_service = WhatsAppEngineService()
    
    # Initial delay to let the system boot
    await asyncio.sleep(20)
    
    while True:
        try:
            logger.info("💓 [KEEP-ALIVE] Pinging WhatsApp Engine to keep it awake...")
            health = engine_service.check_engine_health()
            if health.get("healthy"):
                logger.info("✅ [KEEP-ALIVE] Engine is awake and healthy")
            else:
                logger.warning(f"⚠️ [KEEP-ALIVE] Engine ping returned unhealthy: {health.get('error')}")
        except Exception as e:
            logger.error(f"❌ [KEEP-ALIVE] Failed to ping engine: {str(e)}")
        
        # Ping every 10 minutes (Render spins down after 15 mins of inactivity)
        await asyncio.sleep(600)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for safe background task handling"""
    logger.info("Starting up WhatsApp Platform Backend...")
    logger.info(f"WhatsApp Engine URL Loaded: {settings.WHATSAPP_ENGINE_BASE_URL}")
    
    # Create database tables
    init_db()
    
    # Start background services
    logger.info("🔄 Starting Google Sheets automation background processing...")
    
    # Start Google Sheets polling (Automated hard code removed intentionally)
    # from services.background_task_manager import BackgroundTaskManager
    # task_manager = BackgroundTaskManager()
    # polling_task = asyncio.create_task(task_manager.run_google_sheets_polling(interval_seconds=30))
    # background_tasks.append(polling_task)
    # logger.info("✅ Google Sheets automation background processing started")
    
    # 🔥 [SYSTEM_PERFORMANCE] Disabled auto-start on boot per request to keep system fast
    # from api.google_sheets import start_all_enabled_triggers
    # start_all_enabled_triggers()
    
    # Schedule campaign tasks
    from tasks.campaign_tasks import schedule_daily_tasks
    schedule_daily_tasks()
    
    # 🔥 [KEEP-ALIVE] Start the engine keep-alive task
    logger.info("💓 Starting WhatsApp Engine keep-alive background task...")
    ka_task = asyncio.create_task(keep_engine_alive())
    ka_task.set_name("EngineKeepAlive")
    background_tasks.append(ka_task)
    
    logger.info("🚀 FastAPI application startup completed - ready to serve requests")
    yield
    
    # Graceful shutdown
    logger.info("Shutting down WhatsApp Platform Backend...")
    
    # Cancel all background tasks
    for task in background_tasks:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
            
    logger.info("✅ Shutdown completed")

app = FastAPI(
    title="WhatsApp Platform API",
    description="Backend API for WhatsApp Platform",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://192.168.1.53:3000",
        "http://localhost:3002",
        "http://127.0.0.1:3002",
        "https://whatsapp-platform-backend-ztwa.onrender.com/api",
        "https://whatsapp-platform-frontend-oz5q.onrender.com",
        "https://whatsapp-platform-engine.onrender.com",
       
       
    ],
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Include routers
app.include_router(reseller_router, prefix="/api/resellers")
app.include_router(business_router, prefix="/api/busi_users")

app.include_router(credit_distribution_router, prefix="/api")
app.include_router(devices_router, prefix="/api/devices")
app.include_router(device_sessions_router, prefix="/api")

# Credits API (v1)
app.include_router(credits_router, prefix="/api/v1/credits")
# [COMPATIBILITY] Allow access for v1 credits without /api prefix
app.include_router(credits_router, prefix="/v1/credits", tags=["Compatibility"])

app.include_router(message_usage_router, prefix="/api/message-usage", tags=["Message Usage & Credit Log"])
app.include_router(reseller_analytics_router, prefix="/api/reseller-analytics", tags=["Reseller Analytics Dashboard"])
app.include_router(official_whatsapp_config_router, prefix="/api/official-whatsapp", tags=["Official WhatsApp Config"])

# Include whatsapp API
app.include_router(whatsapp_router, prefix="/api/whatsapp")


# Include user API (Self-Service)
app.include_router(user_router, prefix="/api/user")


# Include token validation API
app.include_router(token_validation_router, prefix="/api")

# Include auth API
app.include_router(auth_router, prefix="/api/auth")

# Include Google Sheets API
app.include_router(google_sheets_router, prefix="/api/google-sheets")



# 🧨 STEP 5: ADD DEVICE SYNC API
from api.device_sync import router as device_sync_router
app.include_router(device_sync_router, prefix="/api/devices", tags=["Device Sync"])

# 🧨 STEP 6: SETUP ERROR HANDLERS
from api.error_handlers import setup_error_handlers
setup_error_handlers(app)

# Include unofficial public API
app.include_router(unofficial_public_api_router, prefix="/api/unofficial", tags=["Unofficial Public API"])

# Include official public API
app.include_router(official_public_api_router, prefix="/api/official", tags=["Official Public API"])


# Include webhooks router
app.include_router(webhooks_router, prefix="/api/webhooks", tags=["Webhooks"])

# Include replies router
app.include_router(replies_router, prefix="/api/replies", tags=["Replies"])

# Include groups router
app.include_router(groups_router, prefix="/api/groups", tags=["Groups"])

# Include quick replies router
app.include_router(quick_replies_router, prefix="/api/quick-replies", tags=["Quick Replies"])

# Include campaigns API
app.include_router(campaigns_router, prefix="/api/campaign", tags=["Campaign API"])

# Include Audit Logs API
app.include_router(audit_logs_router, prefix="/api/audit-logs", tags=["Audit Activity Logs"])


# [COMPATIBILITY] Allow access without /api prefix for common routes
# Since we removed internal prefixes from routers, we explicitly set them here.
app.include_router(auth_router, prefix="/auth", tags=["Compatibility"])
app.include_router(user_router, prefix="/user", tags=["Compatibility"])
app.include_router(business_router, prefix="/busi_users", tags=["Compatibility"])
app.include_router(reseller_router, prefix="/resellers", tags=["Compatibility"])
app.include_router(groups_router, prefix="/groups", tags=["Compatibility"])
app.include_router(replies_router, prefix="/replies", tags=["Compatibility"])
app.include_router(campaigns_router, prefix="/campaign", tags=["Compatibility"])
app.include_router(quick_replies_router, prefix="/quick-replies", tags=["Compatibility"])
app.include_router(google_sheets_router, prefix="/google-sheets", tags=["Compatibility"])
app.include_router(devices_router, prefix="/devices", tags=["Compatibility"])
app.include_router(official_whatsapp_config_router, prefix="/official-whatsapp", tags=["Compatibility"])
app.include_router(unofficial_public_api_router, prefix="/unofficial", tags=["Compatibility"])
app.include_router(official_public_api_router, prefix="/official", tags=["Compatibility"])





@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "WhatsApp Platform Backend API",
        "version": "1.0.0",
        "docs": "/docs",
        "redoc": "/redoc"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "WhatsApp Platform Backend"}

@app.get("/health/db")
async def database_health_check(db = Depends(get_db)):
    """Database health check point to verify connection pool health"""
    try:
        db.execute(text("SELECT 1"))
        return {"status": "healthy", "service": "PostgreSQL Database"}
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return JSONResponse(status_code=503, content={"status": "unhealthy", "error": str(e)})


@app.get("/health/background")
async def background_tasks_health():
    """Check health of background tasks"""
    task_status = []
    for task in background_tasks:
        status = {
            "name": task.get_name(),
            "done": task.done(),
            "cancelled": task.cancelled(),
            "exception": str(task.exception()) if task.exception() else None
        }
        task_status.append(status)
    
    return {
        "status": "healthy",
        "background_tasks": task_status,
        "total_tasks": len(background_tasks)
    }


@app.get("/test-qr/{device_id}")
async def test_qr_endpoint(device_id: str):
    """Test QR endpoint that bypasses database and directly calls WhatsApp Engine."""
    try:
        import requests
        response = requests.get(f"{settings.WHATSAPP_ENGINE_BASE_URL}/session/{device_id}/qr", timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data.get('qr'):
                return {"qr_code": data['qr'], "status": "success"}
            else:
                return {"qr_code": None, "status": data.get('status', 'generating')}
        else:
            return {"error": f"Engine returned {response.status_code}"}
    except Exception as e:
        return {"error": str(e)}


@app.get("/sync-devices/{user_id}")
async def sync_devices_endpoint(user_id: str):
    """DEPRECATED: Use POST /api/devices/sync-devices instead. This endpoint is rate-limited."""
    try:
        import requests
        from db.session import get_db
        from services.device_sync_service import device_sync_service
        import time
        
        # Simple rate limiting - only allow once per 30 seconds per user
        current_time = time.time()
        if not hasattr(sync_devices_endpoint, '_last_sync'):
            sync_devices_endpoint._last_sync = {}
        
        if user_id in sync_devices_endpoint._last_sync:
            if current_time - sync_devices_endpoint._last_sync[user_id] < 30:
                return {"error": "Rate limited. Please wait 30 seconds between sync requests."}
        
        sync_devices_endpoint._last_sync[user_id] = current_time
        
        # Get database session
        db = next(get_db())
        
        # Validate user_id format
        try:
            import uuid
            uuid.UUID(user_id)
        except ValueError:
            return {"error": "Invalid user_id format"}
        
        # Use the proper device sync service
        sync_result = device_sync_service.sync_user_devices(db, user_id)
        
        if sync_result["success"]:
            # Get updated devices from database
            from services.device_service import DeviceService
            device_service = DeviceService(db)
            devices = device_service.get_devices_by_user(user_id)
            
            # Convert to response format
            device_list = []
            for device in devices:
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
            
            return device_list
        else:
            return {"error": sync_result.get("error", "Sync failed")}
            
    except Exception as e:
        logger.error(f"Sync devices error: {e}")
        return {"error": str(e)}


if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=False if os.environ.get("PORT") else True, # Disable reload in production
        log_level="info"
    )


# Reload trigger 3
