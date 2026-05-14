"""
AI Customer Care Backend
Mobile Accessories + SaaS Business
Multi-language: Bangla, English, + Auto Detect
"""

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import Optional, List
import asyncio
import json
import uvicorn
from datetime import datetime

from ai_engine import AIEngine
from knowledge_base import KnowledgeBase
from conversation_manager import ConversationManager
from database import Database

# ─── App Setup ───────────────────────────────────────────────
app = FastAPI(
    title="AI Customer Care API",
    description="Mobile Accessories + SaaS Customer Care AI",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Production এ নির্দিষ্ট domain দিন
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Initialize Services ─────────────────────────────────────
db = Database()
kb = KnowledgeBase()
ai = AIEngine(knowledge_base=kb)
conv_manager = ConversationManager(db=db)
security = HTTPBearer(auto_error=False)

# ─── WebSocket Manager ────────────────────────────────────────
class WebSocketManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active_connections.append(ws)

    def disconnect(self, ws: WebSocket):
        self.active_connections.remove(ws)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except:
                pass

ws_manager = WebSocketManager()

# ─── Request Models ───────────────────────────────────────────
class ChatRequest(BaseModel):
    customer_id: str
    message: str
    platform: str = "web"          # web | whatsapp | telegram
    phone: Optional[str] = None
    language: Optional[str] = None # auto detect if None

class ManualReplyRequest(BaseModel):
    conversation_id: str
    message: str
    agent_name: str = "Support Agent"

class AIToggleRequest(BaseModel):
    conversation_id: str
    enabled: bool

class TrainRequest(BaseModel):
    question: str
    answer: str
    category: str = "general"
    language: str = "auto"

class OrderRequest(BaseModel):
    order_id: str
    customer_id: str

# ─── Main Chat Endpoint ───────────────────────────────────────
@app.post("/api/chat")
async def chat(req: ChatRequest):
    try:
        # ১. Conversation লোড বা নতুন তৈরি
        conversation = await conv_manager.get_or_create(
            customer_id=req.customer_id,
            platform=req.platform,
            phone=req.phone
        )

        # ২. AI বন্ধ থাকলে manual queue তে পাঠাও
        if not conversation.get("ai_enabled", True):
            await db.add_pending_message(conversation["id"], req.message)
            await ws_manager.broadcast({
                "type": "new_message",
                "conversation_id": conversation["id"],
                "customer_id": req.customer_id,
                "message": req.message,
                "platform": req.platform,
                "ai_enabled": False,
                "timestamp": datetime.now().isoformat()
            })
            return {
                "status": "queued",
                "message": "আপনার মেসেজ পেয়েছি। একজন এজেন্ট শীঘ্রই রিপ্লাই করবেন।",
                "conversation_id": conversation["id"]
            }

        # ৩. AI দিয়ে রিপ্লাই তৈরি
        response = await ai.generate_response(
            message=req.message,
            customer_id=req.customer_id,
            conversation_history=conversation.get("history", []),
            language=req.language,
            platform=req.platform
        )

        # ৪. Conversation সেভ করো
        await conv_manager.add_message(
            conversation_id=conversation["id"],
            user_message=req.message,
            ai_response=response["reply"],
            detected_language=response["language"],
            intent=response["intent"]
        )

        # ৫. Dashboard এ live update পাঠাও
        await ws_manager.broadcast({
            "type": "ai_reply",
            "conversation_id": conversation["id"],
            "customer_id": req.customer_id,
            "user_message": req.message,
            "ai_reply": response["reply"],
            "intent": response["intent"],
            "language": response["language"],
            "platform": req.platform,
            "confidence": response.get("confidence", 1.0),
            "timestamp": datetime.now().isoformat()
        })

        return {
            "status": "success",
            "reply": response["reply"],
            "intent": response["intent"],
            "language": response["language"],
            "conversation_id": conversation["id"],
            "suggestions": response.get("suggestions", [])
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── WhatsApp Webhook ─────────────────────────────────────────
@app.post("/webhook/whatsapp")
async def whatsapp_webhook(data: dict):
    """Meta WhatsApp Business API Webhook"""
    try:
        if data.get("object") == "whatsapp_business_account":
            for entry in data.get("entry", []):
                for change in entry.get("changes", []):
                    value = change.get("value", {})
                    messages = value.get("messages", [])

                    for msg in messages:
                        if msg.get("type") == "text":
                            phone = msg["from"]
                            text = msg["text"]["body"]

                            # Chat endpoint এ ফরোয়ার্ড করো
                            chat_req = ChatRequest(
                                customer_id=f"wa_{phone}",
                                message=text,
                                platform="whatsapp",
                                phone=phone
                            )
                            await chat(chat_req)

        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


@app.get("/webhook/whatsapp")
async def whatsapp_verify(
    hub_mode: str = None,
    hub_challenge: str = None,
    hub_verify_token: str = None
):
    """Meta Webhook Verification"""
    from config import settings
    if hub_verify_token == settings.WHATSAPP_VERIFY_TOKEN:
        return int(hub_challenge)
    raise HTTPException(status_code=403, detail="Invalid verify token")


# ─── Baileys Webhook (WhatsApp Web Automation) ────────────────
@app.post("/webhook/baileys")
async def baileys_webhook(data: dict):
    """Node.js Baileys থেকে মেসেজ আসবে"""
    try:
        phone = data.get("from", "")
        text = data.get("message", "")
        
        if not text or not phone:
            return {"status": "skip"}

        chat_req = ChatRequest(
            customer_id=f"baileys_{phone}",
            message=text,
            platform="whatsapp_web",
            phone=phone
        )
        result = await chat(chat_req)
        return result
    except Exception as e:
        return {"status": "error", "detail": str(e)}


# ─── Manual Agent Reply ───────────────────────────────────────
@app.post("/api/manual-reply")
async def manual_reply(req: ManualReplyRequest):
    """Agent নিজে রিপ্লাই দেবেন"""
    await conv_manager.add_agent_message(
        conversation_id=req.conversation_id,
        message=req.message,
        agent_name=req.agent_name
    )

    await ws_manager.broadcast({
        "type": "manual_reply",
        "conversation_id": req.conversation_id,
        "message": req.message,
        "agent_name": req.agent_name,
        "timestamp": datetime.now().isoformat()
    })

    return {"status": "sent"}


# ─── AI Toggle ────────────────────────────────────────────────
@app.post("/api/toggle-ai")
async def toggle_ai(req: AIToggleRequest):
    """নির্দিষ্ট কথোপকথনে AI চালু/বন্ধ"""
    await conv_manager.toggle_ai(req.conversation_id, req.enabled)
    return {
        "status": "updated",
        "ai_enabled": req.enabled,
        "message": f"AI {'চালু' if req.enabled else 'বন্ধ'} করা হয়েছে"
    }


# ─── AI Training ──────────────────────────────────────────────
@app.post("/api/train")
async def train_ai(req: TrainRequest):
    """নতুন FAQ যোগ করো"""
    await kb.add_knowledge(
        question=req.question,
        answer=req.answer,
        category=req.category,
        language=req.language
    )
    return {"status": "trained", "message": "AI শিখে গেছে! ✅"}


# ─── Order Tracking ───────────────────────────────────────────
@app.get("/api/order/{order_id}")
async def get_order(order_id: str):
    order = await db.get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="অর্ডার পাওয়া যায়নি")
    return order


# ─── Dashboard Stats ──────────────────────────────────────────
@app.get("/api/stats")
async def get_stats():
    return await db.get_dashboard_stats()


@app.get("/api/conversations")
async def get_conversations(
    platform: Optional[str] = None,
    limit: int = 50
):
    return await db.get_conversations(platform=platform, limit=limit)


@app.get("/api/conversations/{conversation_id}")
async def get_conversation(conversation_id: str):
    conv = await db.get_conversation(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Not found")
    return conv


# ─── WebSocket Live Feed ──────────────────────────────────────
@app.websocket("/ws/dashboard")
async def websocket_dashboard(ws: WebSocket):
    await ws_manager.connect(ws)
    try:
        # সংযোগের সাথে সাথে stats পাঠাও
        stats = await db.get_dashboard_stats()
        await ws.send_json({"type": "init", "stats": stats})
        
        while True:
            data = await ws.receive_text()
            # Agent এর ping handle
            if data == "ping":
                await ws.send_text("pong")
    except WebSocketDisconnect:
        ws_manager.disconnect(ws)


# ─── Health Check ─────────────────────────────────────────────
@app.get("/health")
async def health():
    return {
        "status": "running ✅",
        "service": "AI Customer Care",
        "version": "1.0.0",
        "timestamp": datetime.now().isoformat()
    }


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
