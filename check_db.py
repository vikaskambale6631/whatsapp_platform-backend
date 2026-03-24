import sys
import os

# Add current directory to path
sys.path.append(os.getcwd())

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models.device import Device
from db.base import engine

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
db = SessionLocal()

try:
    devices = db.query(Device).all()
    with open("db_status.txt", "w") as f:
        f.write(f"Total devices: {len(devices)}\n")
        f.write("-" * 80 + "\n")
        for d in devices:
            d_type = d.device_type.value if hasattr(d.device_type, 'value') else str(d.device_type)
            d_status = d.session_status.value if hasattr(d.session_status, 'value') else str(d.session_status)
            f.write(f"ID: {d.device_id} | User: {d.busi_user_id} | Name: {d.device_name} | Type: {d_type} | Status: {d_status} | Active: {d.is_active}\n")
    print("DONE: State written to db_status.txt")
except Exception as e:
    print(f"ERROR: {e}")
finally:
    db.close()
