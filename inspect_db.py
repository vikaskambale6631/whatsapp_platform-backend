
from db.session import SessionLocal
from models.campaign import Campaign, MessageTemplate
import json

def inspect_latest_campaign():
    db = SessionLocal()
    try:
        latest_campaign = db.query(Campaign).order_by(Campaign.created_at.desc()).first()
        if not latest_campaign:
            print("No campaigns found.")
            return

        print(f"Latest Campaign ID: {latest_campaign.id}")
        print(f"Status: {latest_campaign.status}")
        print(f"Name: {latest_campaign.name}")
        
        templates = db.query(MessageTemplate).filter(MessageTemplate.campaign_id == latest_campaign.id).all()
        print(f"\nFound {len(templates)} templates:")
        for t in templates:
            print(f"- ID: {t.id}")
            print(f"  Content: {t.content}")
            print(f"  Media URL: {t.media_url}")
            print(f"  Media Type: {t.media_type}")
            print("-" * 20)

    except Exception as e:
        print(f"Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    inspect_latest_campaign()
