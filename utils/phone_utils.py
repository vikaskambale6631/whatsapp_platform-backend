import re

def normalize_phone(phone: str | None, default_cc: str = "91") -> str | None:
    if not phone:
        return None

    phone = str(phone).strip()

    # If JID format exists, extract number before "@"
    if "@" in phone:
        phone = phone.split("@")[0]

    # Remove all non-digit characters
    phone = re.sub(r"\D", "", phone)

    # Auto-add country code for 10-digit numbers (common for India)
    if len(phone) == 10:
        phone = f"{default_cc}{phone}"
    elif len(phone) == 11 and phone.startswith("0"):
        # Handle cases like 08767647149
        phone = f"{default_cc}{phone[1:]}"

    # Valid WhatsApp numbers are usually 10–16 digits
    if len(phone) < 10 or len(phone) > 16:
        return None

    return phone
