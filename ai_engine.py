"""
AI Engine
- Claude API ব্যবহার করে সব ভাষায় রিপ্লাই দেয়
- Intent Detection (অর্ডার, অভিযোগ, FAQ, etc.)
- Mobile Accessories + SaaS বিশেষজ্ঞ
"""

import anthropic
import json
import re
from typing import Optional
from config import settings
from knowledge_base import KnowledgeBase

class AIEngine:
    def __init__(self, knowledge_base: KnowledgeBase):
        self.client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        self.kb = knowledge_base
        self.model = "claude-sonnet-4-20250514"

    # ─── System Prompt ────────────────────────────────────────
    def _build_system_prompt(self, platform: str, extra_knowledge: str) -> str:
        return f"""আপনি একজন বিশেষজ্ঞ Customer Care AI Assistant।

## আপনার পরিচয়:
- নাম: Sara AI 🤖
- কাজ: Mobile Accessories ও SaaS সফটওয়্যার কাস্টমার কেয়ার
- Platform: {platform}

## আপনার দায়িত্ব:
১. পণ্য সম্পর্কিত প্রশ্নের উত্তর দেওয়া (Mobile Accessories)
২. SaaS সফটওয়্যার সাপোর্ট দেওয়া
৩. অর্ডার ট্র্যাকিং সাহায্য করা
৪. অভিযোগ গ্রহণ ও সমাধান করা
৫. রিফান্ড/রিটার্ন গাইড করা

## ভাষা নীতি:
- কাস্টমার যে ভাষায় কথা বলবে, সেই ভাষায় উত্তর দাও
- বাংলা, English, হিন্দি, আরবি - সব ভাষা সাপোর্ট করো
- মিশ্র ভাষায় (Banglish) কথা বললে বাংলায় উত্তর দাও

## আচরণ নির্দেশিকা:
- সবসময় বিনয়ী ও সহানুভূতিশীল হও
- সংক্ষিপ্ত কিন্তু সম্পূর্ণ উত্তর দাও
- ইমোজি ব্যবহার করো (WhatsApp এ বেশি, Web এ কম)
- জরুরি সমস্যায় human agent এর কথা বলো

## প্রোডাক্ট জ্ঞান:
{extra_knowledge}

## Intent গুলো চিনতে পারো:
- order_tracking: অর্ডার কোথায়, ডেলিভারি কবে
- complaint: সমস্যা, নষ্ট, কাজ হচ্ছে না
- refund_return: ফেরত, রিফান্ড, টাকা ফেরত
- product_info: পণ্যের দাম, বিবরণ, স্পেসিফিকেশন
- saas_support: সফটওয়্যার সমস্যা, লগইন, ফিচার
- payment: পেমেন্ট, বিল, ইনভয়েস
- general: সাধারণ প্রশ্ন

## উত্তর ফরম্যাট (JSON):
{{
  "reply": "কাস্টমারের উত্তর",
  "intent": "detected_intent",
  "language": "detected_language",
  "confidence": 0.95,
  "needs_human": false,
  "suggestions": ["পরবর্তী প্রশ্নের সাজেশন ১", "সাজেশন ২"],
  "action": null
}}

শুধু JSON রিটার্ন করো, অন্য কিছু না।"""

    # ─── Generate Response ────────────────────────────────────
    async def generate_response(
        self,
        message: str,
        customer_id: str,
        conversation_history: list,
        language: Optional[str] = None,
        platform: str = "web"
    ) -> dict:
        try:
            # Knowledge Base থেকে প্রাসঙ্গিক তথ্য খোঁজো
            relevant_knowledge = await self.kb.search(message)
            knowledge_text = self._format_knowledge(relevant_knowledge)

            # System prompt তৈরি করো
            system = self._build_system_prompt(platform, knowledge_text)

            # Conversation history তৈরি করো
            messages = self._build_messages(conversation_history, message)

            # Claude API কল
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1000,
                system=system,
                messages=messages
            )

            # Response parse করো
            raw = response.content[0].text.strip()
            result = self._parse_response(raw)
            return result

        except Exception as e:
            # Fallback response
            return {
                "reply": "দুঃখিত, এই মুহূর্তে সমস্যা হচ্ছে। অনুগ্রহ করে একটু পরে আবার চেষ্টা করুন অথবা আমাদের হেল্পলাইনে কল করুন। 🙏",
                "intent": "error",
                "language": "bn",
                "confidence": 0.0,
                "needs_human": True,
                "suggestions": [],
                "error": str(e)
            }

    # ─── Build Messages ───────────────────────────────────────
    def _build_messages(self, history: list, current_message: str) -> list:
        messages = []

        # শেষ ১০টি বার্তা রাখো (context window বাঁচাতে)
        recent_history = history[-10:] if len(history) > 10 else history

        for item in recent_history:
            messages.append({"role": "user", "content": item["user"]})
            messages.append({"role": "assistant", "content": item["assistant"]})

        # বর্তমান মেসেজ যোগ করো
        messages.append({"role": "user", "content": current_message})
        return messages

    # ─── Format Knowledge ─────────────────────────────────────
    def _format_knowledge(self, knowledge_items: list) -> str:
        if not knowledge_items:
            return "সাধারণ কাস্টমার কেয়ার নীতি অনুসরণ করো।"

        text = ""
        for item in knowledge_items:
            text += f"প্রশ্ন: {item['question']}\n"
            text += f"উত্তর: {item['answer']}\n\n"
        return text

    # ─── Parse Response ───────────────────────────────────────
    def _parse_response(self, raw: str) -> dict:
        try:
            # JSON block থেকে বের করো
            json_match = re.search(r'\{.*\}', raw, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
        except:
            pass

        # Fallback: plain text কে wrap করো
        return {
            "reply": raw,
            "intent": "general",
            "language": "auto",
            "confidence": 0.8,
            "needs_human": False,
            "suggestions": []
        }
