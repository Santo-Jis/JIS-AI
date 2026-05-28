"""
AI Engine — Tool Calling যুক্ত (আপডেট)
- Claude API ব্যবহার করে সব ভাষায় রিপ্লাই দেয়
- Intent Detection (অর্ডার, অভিযোগ, FAQ, etc.)
- Novatech-BD থেকে Live Product Data আনে (Tool Calling)
- Mobile Accessories + SaaS বিশেষজ্ঞ

পরিবর্তন (আগের ai_engine.py থেকে):
  ✅ Tool Calling যোগ হয়েছে — 2-pass approach
  ✅ Pass 1: AI বলে কোন tool দরকার
  ✅ Pass 2: Tool data নিয়ে AI final উত্তর দেয়
  ✅ Tool ছাড়া সাধারণ প্রশ্নে আগের মতোই কাজ করে
"""

import anthropic
import json
import re
from typing import Optional
from config import settings
from knowledge_base import KnowledgeBase
from tool_calling import (       # ← নতুন import
    PRODUCT_TOOLS,
    execute_tool,
    parse_tool_call,
    get_tools_description,
)


class AIEngine:
    def __init__(self, knowledge_base: KnowledgeBase):
        self.client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        self.kb = knowledge_base
        self.model = "claude-sonnet-4-20250514"

    # ─── Pass-1 System Prompt (Tool Detection) ────────────────
    def _build_tool_detection_prompt(self) -> str:
        tools_text = get_tools_description()
        return f"""তুমি একটি tool selector।
Customer এর প্রশ্ন দেখো এবং কোন tool দরকার তা বলো।

## Available Tools:
{tools_text}

## নিয়ম:
- পণ্যের নাম বললে search_product ব্যবহার করো, params এ keyword দাও
- stock বা availability জিজ্ঞেস করলে check_stock, params এ keyword দাও
- Order ID বা tracking দিলে get_order_status, params এ order_id দাও
- সব পণ্য বা catalog চাইলে get_product_catalog
- ডেলিভারি সম্পর্কে জিজ্ঞেস করলে get_delivery_info
- সাধারণ কথা, অভিযোগ, রিফান্ড, অন্য কোনো বিষয় → tool: "none"

## Response Format (শুধু JSON, অন্য কিছু না):
{{"tool": "tool_name_or_none", "params": {{"keyword": "পণ্যের নাম"}}}}

উদাহরণ:
  প্রশ্ন: "চার্জার আছে?" → {{"tool": "search_product", "params": {{"keyword": "চার্জার"}}}}
  প্রশ্ন: "ORD-001 কোথায়?" → {{"tool": "get_order_status", "params": {{"order_id": "ORD-001"}}}}
  প্রশ্ন: "রিফান্ড কিভাবে?" → {{"tool": "none", "params": {{}}}}
  প্রশ্ন: "পণ্যের তালিকা দাও" → {{"tool": "get_product_catalog", "params": {{}}}}
"""

    # ─── Pass-2 System Prompt (Final Answer) ──────────────────
    def _build_system_prompt(self, platform: str, extra_knowledge: str,
                              tool_data: Optional[dict] = None) -> str:
        tool_section = ""
        if tool_data and tool_data.get("success"):
            tool_section = f"""
## 🔴 Live Data (Novatech DB থেকে — এটাই সঠিক, এটা ব্যবহার করো):
{json.dumps(tool_data, ensure_ascii=False, indent=2)}
"""

        return f"""আপনি একজন বিশেষজ্ঞ Customer Care AI Assistant।

## আপনার পরিচয়:
- নাম: Sara AI 🤖
- কাজ: Mobile Accessories ও SaaS সফটওয়্যার কাস্টমার কেয়ার
- Platform: {platform}
{tool_section}
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
- Live Data থাকলে সেটাই ব্যবহার করো, অনুমান করো না

## FAQ থেকে অতিরিক্ত জ্ঞান:
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

    # ─── Generate Response (আপডেট — Tool Calling যুক্ত) ───────
    async def generate_response(
        self,
        message: str,
        customer_id: str,
        conversation_history: list,
        language: Optional[str] = None,
        platform: str = "web"
    ) -> dict:
        try:
            # ── Knowledge Base থেকে FAQ খোঁজো ─────────────────
            relevant_knowledge = await self.kb.search(message)
            knowledge_text = self._format_knowledge(relevant_knowledge)

            # ── Pass 1: Tool Detection ──────────────────────────
            tool_data = None
            tool_detection_prompt = self._build_tool_detection_prompt()

            detection_response = self.client.messages.create(
                model=self.model,
                max_tokens=150,          # Tool detection এ বেশি token দরকার নেই
                system=tool_detection_prompt,
                messages=[{"role": "user", "content": message}]
            )
            detection_text = detection_response.content[0].text.strip()
            tool_call = parse_tool_call(detection_text)

            # ── Tool Execute করো (যদি দরকার হয়) ────────────────
            if tool_call and tool_call["tool"] != "none":
                tool_data = await execute_tool(
                    tool_name=tool_call["tool"],
                    params=tool_call.get("params", {}),
                    customer_phone=customer_id  # customer_id = WhatsApp phone number
                )

            # ── Pass 2: Final Answer ────────────────────────────
            system = self._build_system_prompt(platform, knowledge_text, tool_data)
            messages = self._build_messages(conversation_history, message)

            response = self.client.messages.create(
                model=self.model,
                max_tokens=1000,
                system=system,
                messages=messages
            )

            raw = response.content[0].text.strip()
            result = self._parse_response(raw)

            # Tool info যোগ করো (debug / analytics এর জন্য)
            result["tool_used"] = tool_call["tool"] if tool_call else None

            return result

        except Exception as e:
            return {
                "reply": "দুঃখিত, এই মুহূর্তে সমস্যা হচ্ছে। অনুগ্রহ করে একটু পরে আবার চেষ্টা করুন অথবা আমাদের হেল্পলাইনে কল করুন। 🙏",
                "intent": "error",
                "language": "bn",
                "confidence": 0.0,
                "needs_human": True,
                "suggestions": [],
                "tool_used": None,
                "error": str(e)
            }

    # ─── Build Messages ────────────────────────────────────────
    def _build_messages(self, history: list, current_message: str) -> list:
        messages = []
        recent_history = history[-10:] if len(history) > 10 else history
        for item in recent_history:
            messages.append({"role": "user", "content": item["user"]})
            messages.append({"role": "assistant", "content": item["assistant"]})
        messages.append({"role": "user", "content": current_message})
        return messages

    # ─── Format Knowledge ──────────────────────────────────────
    def _format_knowledge(self, knowledge_items: list) -> str:
        if not knowledge_items:
            return "সাধারণ কাস্টমার কেয়ার নীতি অনুসরণ করো।"
        text = ""
        for item in knowledge_items:
            text += f"প্রশ্ন: {item['question']}\n"
            text += f"উত্তর: {item['answer']}\n\n"
        return text

    # ─── Parse Response ────────────────────────────────────────
    def _parse_response(self, raw: str) -> dict:
        try:
            json_match = re.search(r'\{.*\}', raw, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
        except Exception:
            pass
        return {
            "reply": raw,
            "intent": "general",
            "language": "auto",
            "confidence": 0.8,
            "needs_human": False,
            "suggestions": []
        }
