"""
Conversation Manager
- Conversation তৈরি ও পরিচালনা করে
"""

import uuid
from database import Database

class ConversationManager:
    def __init__(self, db: Database):
        self.db = db

    async def get_or_create(self, customer_id: str, platform: str, phone: str = None) -> dict:
        # customer_id দিয়ে সক্রিয় conversation খোঁজো
        convs = await self.db.get_conversations(limit=200)
        for conv in convs:
            if conv["customer_id"] == customer_id and conv["status"] == "active":
                return conv

        # নতুন conversation তৈরি করো
        conv_id = str(uuid.uuid4())[:8].upper()
        return await self.db.create_conversation({
            "id": f"CONV-{conv_id}",
            "customer_id": customer_id,
            "platform": platform,
            "phone": phone
        })

    async def add_message(self, conversation_id: str, user_message: str,
                          ai_response: str, detected_language: str = None,
                          intent: str = None):
        await self.db.add_message(conversation_id, "user", user_message)
        await self.db.add_message(
            conversation_id, "assistant", ai_response,
            intent=intent, language=detected_language
        )

    async def add_agent_message(self, conversation_id: str,
                                message: str, agent_name: str):
        await self.db.add_message(
            conversation_id, "agent", message, agent_name=agent_name
        )

    async def toggle_ai(self, conversation_id: str, enabled: bool):
        await self.db.toggle_ai(conversation_id, enabled)
