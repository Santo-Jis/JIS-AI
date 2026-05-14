"""
Knowledge Base
- Mobile Accessories + SaaS এর FAQ
- নতুন জ্ঞান যোগ করা যায় (Training)
- বাংলা + English দুই ভাষায় খোঁজা যায়
"""

import json
import os
from datetime import datetime
from typing import List, Optional

KNOWLEDGE_FILE = "knowledge/knowledge_base.json"

# ─── Default Knowledge ────────────────────────────────────────
DEFAULT_KNOWLEDGE = [
    # Mobile Accessories
    {
        "id": "mob_001",
        "question": "আপনাদের কি ধরনের পণ্য পাওয়া যায়?",
        "answer": "আমাদের কাছে মোবাইল কভার, স্ক্রিন প্রটেক্টর, চার্জার, ইয়ারফোন, পাওয়ার ব্যাংক, ক্যাবল সহ সব ধরনের মোবাইল এক্সেসরিজ পাওয়া যায়। 📱",
        "category": "product_info",
        "language": "bn"
    },
    {
        "id": "mob_002",
        "question": "What products do you sell?",
        "answer": "We sell all types of mobile accessories including phone cases, screen protectors, chargers, earphones, power banks, and cables. 📱",
        "category": "product_info",
        "language": "en"
    },
    {
        "id": "mob_003",
        "question": "পণ্যে ওয়ারেন্টি আছে?",
        "answer": "হ্যাঁ! সব পণ্যে ৬ মাসের ওয়ারেন্টি দেওয়া হয়। পণ্য নষ্ট হলে বা সমস্যা হলে আমাদের সাথে যোগাযোগ করুন। ✅",
        "category": "product_info",
        "language": "bn"
    },
    {
        "id": "mob_004",
        "question": "ডেলিভারি কত দিনে পাবো?",
        "answer": "ঢাকার ভেতরে ১-২ দিন, ঢাকার বাইরে ৩-৫ কার্যদিবসের মধ্যে ডেলিভারি দেওয়া হয়। 🚚",
        "category": "order_tracking",
        "language": "bn"
    },
    {
        "id": "mob_005",
        "question": "How long does delivery take?",
        "answer": "Delivery takes 1-2 days inside Dhaka and 3-5 working days outside Dhaka. 🚚",
        "category": "order_tracking",
        "language": "en"
    },
    {
        "id": "mob_006",
        "question": "পণ্য ফেরত দেওয়া যাবে?",
        "answer": "হ্যাঁ! পণ্য পাওয়ার ৭ দিনের মধ্যে ফেরত দিতে পারবেন। পণ্য অক্ষত থাকতে হবে এবং অরিজিনাল প্যাকেজিং সহ ফেরত দিতে হবে। 📦",
        "category": "refund_return",
        "language": "bn"
    },
    {
        "id": "mob_007",
        "question": "রিফান্ড পেতে কতদিন লাগে?",
        "answer": "রিফান্ড প্রক্রিয়া সম্পন্ন হতে ৩-৫ কার্যদিবস লাগে। টাকা আপনার মোবাইল ব্যাংকিং বা ব্যাংক একাউন্টে পাঠানো হবে। 💳",
        "category": "refund_return",
        "language": "bn"
    },
    # SaaS Support
    {
        "id": "saas_001",
        "question": "সফটওয়্যারে লগইন করতে পারছি না",
        "answer": "লগইন সমস্যার জন্য:\n১. পাসওয়ার্ড রিসেট করুন\n২. ব্রাউজার ক্যাশ পরিষ্কার করুন\n৩. অন্য ব্রাউজারে চেষ্টা করুন\nসমস্যা থাকলে আমাদের জানান। 🔧",
        "category": "saas_support",
        "language": "bn"
    },
    {
        "id": "saas_002",
        "question": "I can't login to the software",
        "answer": "For login issues:\n1. Reset your password\n2. Clear browser cache\n3. Try a different browser\nContact us if the problem persists. 🔧",
        "category": "saas_support",
        "language": "en"
    },
    {
        "id": "saas_003",
        "question": "সফটওয়্যারের দাম কত?",
        "answer": "আমাদের SaaS প্ল্যান:\n• Basic: ৳৯৯৯/মাস\n• Professional: ৳১৯৯৯/মাস\n• Enterprise: কাস্টম প্রাইসিং\n\n৭ দিন ফ্রি ট্রায়াল পাবেন! 🎉",
        "category": "product_info",
        "language": "bn"
    },
    {
        "id": "saas_004",
        "question": "How much does the software cost?",
        "answer": "Our SaaS Plans:\n• Basic: $9.99/month\n• Professional: $19.99/month\n• Enterprise: Custom pricing\n\n7-day free trial available! 🎉",
        "category": "product_info",
        "language": "en"
    },
    {
        "id": "saas_005",
        "question": "পেমেন্ট কিভাবে করবো?",
        "answer": "আমরা গ্রহণ করি:\n• বিকাশ, নগদ, রকেট\n• ক্রেডিট/ডেবিট কার্ড\n• ব্যাংক ট্রান্সফার\n• PayPal (আন্তর্জাতিক) 💳",
        "category": "payment",
        "language": "bn"
    },
    {
        "id": "gen_001",
        "question": "যোগাযোগ কিভাবে করবো?",
        "answer": "আমাদের সাথে যোগাযোগ করুন:\n📞 হটলাইন: 01XXXXXXXXX\n📧 Email: support@yourcompany.com\n⏰ সময়: সকাল ৯টা - রাত ১০টা (৭ দিন) 🙏",
        "category": "general",
        "language": "bn"
    },
    {
        "id": "gen_002",
        "question": "How can I contact you?",
        "answer": "Contact us:\n📞 Hotline: 01XXXXXXXXX\n📧 Email: support@yourcompany.com\n⏰ Hours: 9 AM - 10 PM (7 days) 🙏",
        "category": "general",
        "language": "en"
    },
]

class KnowledgeBase:
    def __init__(self):
        self._ensure_file()

    def _ensure_file(self):
        os.makedirs("knowledge", exist_ok=True)
        if not os.path.exists(KNOWLEDGE_FILE):
            with open(KNOWLEDGE_FILE, "w", encoding="utf-8") as f:
                json.dump(DEFAULT_KNOWLEDGE, f, ensure_ascii=False, indent=2)

    def _load(self) -> list:
        with open(KNOWLEDGE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)

    def _save(self, data: list):
        with open(KNOWLEDGE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    async def search(self, query: str, top_k: int = 3) -> List[dict]:
        """সহজ keyword-based search"""
        knowledge = self._load()
        query_lower = query.lower()
        scored = []

        for item in knowledge:
            score = 0
            q_lower = item["question"].lower()
            a_lower = item["answer"].lower()

            # শব্দ মিলালে স্কোর দাও
            for word in query_lower.split():
                if len(word) > 2:
                    if word in q_lower:
                        score += 3
                    if word in a_lower:
                        score += 1

            if score > 0:
                scored.append((score, item))

        # স্কোর অনুযায়ী সাজাও
        scored.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in scored[:top_k]]

    async def add_knowledge(
        self,
        question: str,
        answer: str,
        category: str = "general",
        language: str = "auto"
    ):
        knowledge = self._load()
        new_id = f"custom_{len(knowledge)+1:04d}"
        knowledge.append({
            "id": new_id,
            "question": question,
            "answer": answer,
            "category": category,
            "language": language,
            "added_at": datetime.now().isoformat()
        })
        self._save(knowledge)

    async def get_all(self, category: Optional[str] = None) -> list:
        knowledge = self._load()
        if category:
            return [k for k in knowledge if k["category"] == category]
        return knowledge

    async def delete(self, knowledge_id: str) -> bool:
        knowledge = self._load()
        new_knowledge = [k for k in knowledge if k["id"] != knowledge_id]
        if len(new_knowledge) < len(knowledge):
            self._save(new_knowledge)
            return True
        return False
