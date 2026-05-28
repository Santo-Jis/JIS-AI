"""
WhatsApp Sender Service
FastAPI → Baileys Gateway → WhatsApp

ব্যবহার:
    from whatsapp import send_whatsapp
    await send_whatsapp("01XXXXXXXXX", "আপনার message")
"""

import httpx
import os
from typing import Optional

BAILEYS_URL    = os.getenv("BAILEYS_URL", "http://localhost:3001")
API_SECRET     = os.getenv("API_SECRET",  "change-this-secret")

# ─── Phone Format ──────────────────────────────────────────────

def _format_phone(phone: str) -> str:
    digits = ''.join(filter(str.isdigit, phone))
    if digits.startswith('01') and len(digits) == 11:
        digits = '880' + digits
    if digits.startswith('00'):
        digits = digits[2:]
    return digits

# ─── Send WhatsApp ─────────────────────────────────────────────

async def send_whatsapp(phone: str, message: str) -> dict:
    """
    Baileys Gateway দিয়ে WhatsApp message পাঠাও।
    Error হলেও main flow বন্ধ হবে না।
    """
    try:
        formatted = _format_phone(phone)
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{BAILEYS_URL}/send",
                json={"phone": formatted, "message": message},
                headers={"x-api-secret": API_SECRET}
            )
            data = resp.json()
            if resp.status_code == 200:
                print(f"✅ WhatsApp পাঠানো → {formatted}")
                return {"success": True}
            else:
                print(f"⚠️ WhatsApp failed → {formatted}: {data}")
                return {"success": False, "error": data}

    except Exception as e:
        print(f"❌ WhatsApp error → {phone}: {e}")
        return {"success": False, "error": str(e)}


# ─── Bulk Send ─────────────────────────────────────────────────

async def send_whatsapp_bulk(phones: list, message: str) -> dict:
    """
    একাধিক নম্বরে একই message পাঠাও।
    """
    import asyncio
    results = await asyncio.gather(
        *[send_whatsapp(p, message) for p in phones],
        return_exceptions=True
    )
    sent   = sum(1 for r in results if isinstance(r, dict) and r.get("success"))
    failed = len(phones) - sent
    return {"sent": sent, "failed": failed, "total": len(phones)}
