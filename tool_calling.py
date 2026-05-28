"""
JIS-AI — Tool Calling Service (v2 — ছবি ও অর্ডার যুক্ত)

নতুন Tools:
  ✅ get_product_catalog    — সব পণ্য (আগের মতো)
  ✅ search_product         — নির্দিষ্ট পণ্য খোঁজা + ছবি URL
  ✅ check_stock            — stock আছে কিনা
  ✅ show_product_image     — পণ্যের ছবি WhatsApp-এ পাঠাও
  ✅ place_order            — সরাসরি অর্ডার নাও (phone দিয়ে customer match)
  ✅ get_order_status       — অর্ডার ট্র্যাকিং
  ✅ get_delivery_info      — ডেলিভারি তথ্য
  ✅ cancel_order           — pending অর্ডার বাতিল
"""

import httpx
import json
import os
import re
from typing import Optional

NOVATECH_API_URL    = os.getenv("NOVATECH_API_URL", "https://your-novatech-backend.onrender.com")
NOVATECH_API_SECRET = os.getenv("NOVATECH_API_SECRET", "change-this-secret")
BAILEYS_URL         = os.getenv("BAILEYS_URL", "http://localhost:3001")

# ─── Tool Definitions ──────────────────────────────────────────
PRODUCT_TOOLS = [
    {
        "name": "get_product_catalog",
        "description": "সব পণ্যের তালিকা দেখাও। কেউ 'কি পণ্য আছে', 'product list', 'catalog' জিজ্ঞেস করলে।",
    },
    {
        "name": "search_product",
        "description": "নির্দিষ্ট পণ্য খোঁজো। পণ্যের নাম বললে। যেমন: 'চার্জার', 'Power Bank', 'earphone'।",
        "params": {"keyword": "পণ্যের নাম বাংলা বা English এ"}
    },
    {
        "name": "show_product_image",
        "description": "পণ্যের ছবি WhatsApp-এ পাঠাও। কেউ 'ছবি দেখাও', 'photo দাও', 'দেখতে চাই' বললে। "
                       "আগে search_product করে product_id নাও, তারপর এটা call করো।",
        "params": {"product_id": "UUID", "phone": "customer phone number"}
    },
    {
        "name": "check_stock",
        "description": "পণ্য stock-এ আছে কিনা। 'available?', 'stock আছে?', 'পাওয়া যাবে?' বললে।",
        "params": {"keyword": "পণ্যের নাম"}
    },
    {
        "name": "place_order",
        "description": "সরাসরি অর্ডার নাও। কেউ 'অর্ডার করতে চাই', 'X টা চাই', 'buy করবো' বললে। "
                       "phone number দিয়ে customer match হবে। product_id ও quantity লাগবে।",
        "params": {
            "phone": "customer এর phone number",
            "items": [{"product_id": "UUID", "qty": 1}],
            "note": "অতিরিক্ত কোনো নোট"
        }
    },
    {
        "name": "get_order_status",
        "description": "অর্ডারের অবস্থা দেখো। Order ID বা tracking number দিলে।",
        "params": {"order_id": "order ID"}
    },
    {
        "name": "cancel_order",
        "description": "pending অর্ডার বাতিল করো। কেউ 'অর্ডার বাতিল' বললে।",
        "params": {"order_id": "order ID", "phone": "customer phone"}
    },
    {
        "name": "get_delivery_info",
        "description": "ডেলিভারি সময়, চার্জ, নিয়ম। 'কতদিনে পাবো', 'ডেলিভারি চার্জ' বললে।",
    },
]


# ─── Tool Executor ─────────────────────────────────────────────
async def execute_tool(tool_name: str, params: dict = None, customer_phone: str = None) -> dict:
    params = params or {}
    headers = {"x-api-secret": NOVATECH_API_SECRET}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:

            # ── 1. সব পণ্যের তালিকা ────────────────────────────
            if tool_name == "get_product_catalog":
                resp = await client.get(
                    f"{NOVATECH_API_URL}/api/products-public",
                    headers=headers, params={"is_active": "true"}
                )
                if resp.status_code == 200:
                    products = resp.json().get("data", [])
                    safe = [
                        {
                            "id": p.get("id"),
                            "নাম": p.get("name"),
                            "দাম": f"৳{float(p.get('price') or 0):,.0f}",
                            "unit": p.get("unit"),
                            "stock_আছে": int(p.get("available_stock") or 0) > 0,
                            "ছবি_আছে": bool(p.get("image_url")),
                        }
                        for p in products[:25]
                    ]
                    return {"success": True, "products": safe, "মোট": len(safe),
                            "tip": "ছবি দেখতে পণ্যের নাম বলুন"}

            # ── 2. পণ্য খোঁজা ──────────────────────────────────
            elif tool_name == "search_product":
                keyword = params.get("keyword", "")
                resp = await client.get(
                    f"{NOVATECH_API_URL}/api/products-public",
                    headers=headers, params={"search": keyword, "is_active": "true"}
                )
                if resp.status_code == 200:
                    products = resp.json().get("data", [])
                    if not products:
                        return {"success": True, "found": False,
                                "summary": f"'{keyword}' নামে কোনো পণ্য পাওয়া যায়নি।"}
                    safe = [
                        {
                            "id": p.get("id"),
                            "নাম": p.get("name"),
                            "দাম": f"৳{float(p.get('price') or 0):,.0f}",
                            "unit": p.get("unit"),
                            "stock": int(p.get("available_stock") or 0),
                            "stock_আছে": int(p.get("available_stock") or 0) > 0,
                            "description": (p.get("description") or "")[:100],
                            "image_url": p.get("image_url"),  # ছবি URL সংরক্ষণ
                        }
                        for p in products[:5]
                    ]
                    return {"success": True, "found": True, "products": safe,
                            "tip": "ছবি দেখতে বলুন 'ছবি দেখাও'"}

            # ── 3. ছবি পাঠানো (Baileys এর নতুন endpoint) ─────────
            elif tool_name == "show_product_image":
                product_id = params.get("product_id", "")
                phone      = params.get("phone") or customer_phone

                if not product_id or not phone:
                    return {"success": False, "error": "product_id ও phone দরকার"}

                # Novatech থেকে product detail নাও
                resp = await client.get(
                    f"{NOVATECH_API_URL}/api/products-public/{product_id}",
                    headers=headers
                )
                if resp.status_code != 200:
                    return {"success": False, "error": "পণ্য পাওয়া যায়নি"}

                product = resp.json().get("data", {})
                image_url = product.get("image_url")

                if not image_url:
                    return {"success": False, "no_image": True,
                            "summary": f"{product.get('name')} — এই পণ্যের ছবি নেই। "
                                       f"দাম: ৳{float(product.get('price') or 0):,.0f}"}

                # Baileys-এ image পাঠাও
                baileys_resp = await client.post(
                    f"{BAILEYS_URL}/send-product",
                    headers={"x-api-secret": os.getenv("API_SECRET", "change-this-secret")},
                    json={
                        "phone": phone,
                        "product": {
                            "name":        product.get("name"),
                            "price":       float(product.get("price") or 0),
                            "stock":       int(product.get("available_stock") or 0),
                            "unit":        product.get("unit"),
                            "description": product.get("description"),
                            "image_url":   image_url,
                        }
                    },
                    timeout=15.0
                )

                if baileys_resp.status_code == 200:
                    return {"success": True, "image_sent": True,
                            "summary": f"{product.get('name')} এর ছবি WhatsApp-এ পাঠানো হয়েছে ✅"}
                else:
                    return {"success": False,
                            "summary": "ছবি পাঠাতে সমস্যা হয়েছে। পরে আবার চেষ্টা করুন।"}

            # ── 4. Stock চেক ────────────────────────────────────
            elif tool_name == "check_stock":
                keyword = params.get("keyword", "")
                resp = await client.get(
                    f"{NOVATECH_API_URL}/api/products-public",
                    headers=headers, params={"search": keyword}
                )
                if resp.status_code == 200:
                    products = resp.json().get("data", [])
                    if not products:
                        return {"success": True, "available": False,
                                "summary": f"'{keyword}' পাওয়া যাচ্ছে না।"}
                    p = products[0]
                    stock = int(p.get("available_stock") or 0)
                    return {
                        "success": True,
                        "পণ্য": p.get("name"),
                        "available": stock > 0,
                        "stock": stock,
                        "দাম": f"৳{float(p.get('price') or 0):,.0f}",
                        "product_id": p.get("id"),
                        "summary": f"{p.get('name')}: {'✅ আছে' if stock > 0 else '❌ নেই'}"
                    }

            # ── 5. অর্ডার নেওয়া ────────────────────────────────
            elif tool_name == "place_order":
                phone = params.get("phone") or customer_phone
                items = params.get("items", [])
                note  = params.get("note", "WhatsApp থেকে অর্ডার")

                if not phone or not items:
                    return {"success": False,
                            "error": "phone number ও পণ্যের তথ্য দরকার",
                            "needs_info": True}

                # Phone দিয়ে customer খোঁজো
                cust_resp = await client.get(
                    f"{NOVATECH_API_URL}/api/customer-by-phone",
                    headers=headers, params={"phone": phone}
                )

                if cust_resp.status_code == 404:
                    return {
                        "success": False,
                        "not_registered": True,
                        "summary": "আপনার নম্বরটি আমাদের সিস্টেমে নেই। "
                                   "অর্ডার করতে আমাদের SR-এর সাথে যোগাযোগ করুন অথবা "
                                   "customer portal-এ রেজিস্ট্রেশন করুন।"
                    }

                customer = cust_resp.json().get("data", {})
                customer_id = customer.get("id")

                # Novatech-এ order request তৈরি করো
                order_resp = await client.post(
                    f"{NOVATECH_API_URL}/api/whatsapp-order",
                    headers=headers,
                    json={
                        "customer_id": customer_id,
                        "items":       items,
                        "note":        note,
                        "source":      "whatsapp"
                    }
                )

                if order_resp.status_code == 201:
                    data = order_resp.json().get("data", {})
                    return {
                        "success": True,
                        "order_placed": True,
                        "request_id":   data.get("request_id"),
                        "items_count":  data.get("items_count"),
                        "summary": f"✅ অর্ডার নেওয়া হয়েছে! Request ID: {data.get('request_id')}. "
                                   f"শীঘ্রই আমাদের SR আপনার সাথে যোগাযোগ করবেন।"
                    }
                else:
                    err = order_resp.json().get("message", "অর্ডার নিতে সমস্যা হয়েছে।")
                    return {"success": False, "summary": err}

            # ── 6. অর্ডার স্ট্যাটাস ────────────────────────────
            elif tool_name == "get_order_status":
                order_id = params.get("order_id", "")
                resp = await client.get(
                    f"{NOVATECH_API_URL}/api/order-public/{order_id}",
                    headers=headers
                )
                if resp.status_code == 200:
                    order = resp.json()
                    status_map = {
                        "pending":    "⏳ অপেক্ষামাণ",
                        "confirmed":  "✅ কনফার্ম হয়েছে",
                        "assigned":   "🚴 SR রওনা দিয়েছে",
                        "processing": "🔄 প্রক্রিয়াধীন",
                        "shipped":    "🚚 পাঠানো হয়েছে",
                        "delivered":  "✅ পৌঁছে গেছে",
                        "cancelled":  "❌ বাতিল",
                    }
                    s = order.get("status", "")
                    return {
                        "success": True,
                        "order_id": order_id,
                        "status": status_map.get(s, s),
                        "tracking": order.get("tracking_number") or "এখনো দেওয়া হয়নি",
                        "summary": f"অর্ডার {order_id}: {status_map.get(s, s)}"
                    }
                return {"success": False, "summary": f"অর্ডার '{order_id}' পাওয়া যায়নি।"}

            # ── 7. অর্ডার বাতিল ────────────────────────────────
            elif tool_name == "cancel_order":
                order_id = params.get("order_id", "")
                phone    = params.get("phone") or customer_phone

                resp = await client.post(
                    f"{NOVATECH_API_URL}/api/whatsapp-order-cancel",
                    headers=headers,
                    json={"order_id": order_id, "phone": phone}
                )
                if resp.status_code == 200:
                    return {"success": True, "summary": f"অর্ডার {order_id} বাতিল করা হয়েছে।"}
                err = resp.json().get("message", "বাতিল করা যায়নি।")
                return {"success": False, "summary": err}

            # ── 8. ডেলিভারি তথ্য ───────────────────────────────
            elif tool_name == "get_delivery_info":
                return {
                    "success": True,
                    "ঢাকার_ভেতরে": "১-২ কার্যদিবস",
                    "ঢাকার_বাইরে": "৩-৫ কার্যদিবস",
                    "ডেলিভারি_চার্জ": "ঢাকায় ৳৬০, বাইরে ৳১২০",
                    "ফ্রি_ডেলিভারি": "৳৫০০+ অর্ডারে ঢাকায় ফ্রি",
                    "summary": "ঢাকায় ১-২ দিন (৳৬০), বাইরে ৩-৫ দিন (৳১২০)"
                }

    except httpx.TimeoutException:
        return {"success": False, "error": "Server সাড়া দিচ্ছে না। পরে চেষ্টা করুন।"}
    except Exception as e:
        return {"success": False, "error": str(e)}

    return {"success": False, "error": "অজানা সমস্যা।"}


# ─── Tool Detection Parser ──────────────────────────────────────
def parse_tool_call(text: str) -> Optional[dict]:
    try:
        match = re.search(r'\{[\s\S]*?"tool"\s*:\s*"([^"]+)"[\s\S]*?\}', text)
        if not match:
            return None
        parsed = json.loads(match.group())
        valid  = [t["name"] for t in PRODUCT_TOOLS]
        if parsed.get("tool") not in valid:
            return None
        return {"tool": parsed["tool"], "params": parsed.get("params", {})}
    except Exception:
        return None


def get_tools_description() -> str:
    return "\n".join(f"- {t['name']}: {t['description']}" for t in PRODUCT_TOOLS)
