"""
Database Manager
- SQLite (সহজ, VPS এ আলাদা সেটআপ লাগে না)
- Conversations, Messages, Orders, Stats সেভ করে
"""

import aiosqlite
import json
from datetime import datetime
from typing import Optional
import os

DB_PATH = "data/customer_care.db"

class Database:
    def __init__(self):
        os.makedirs("data", exist_ok=True)

    async def _get_db(self):
        return await aiosqlite.connect(DB_PATH)

    async def initialize(self):
        """প্রথমবার চালালে টেবিল তৈরি করো"""
        async with await self._get_db() as db:
            await db.executescript("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    customer_id TEXT NOT NULL,
                    platform TEXT DEFAULT 'web',
                    phone TEXT,
                    ai_enabled INTEGER DEFAULT 1,
                    status TEXT DEFAULT 'active',
                    created_at TEXT,
                    updated_at TEXT
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    intent TEXT,
                    language TEXT,
                    agent_name TEXT,
                    timestamp TEXT,
                    FOREIGN KEY (conversation_id) REFERENCES conversations(id)
                );

                CREATE TABLE IF NOT EXISTS orders (
                    id TEXT PRIMARY KEY,
                    customer_id TEXT,
                    customer_name TEXT,
                    phone TEXT,
                    items TEXT,
                    total_amount REAL,
                    status TEXT DEFAULT 'processing',
                    tracking_number TEXT,
                    address TEXT,
                    created_at TEXT,
                    updated_at TEXT
                );

                CREATE TABLE IF NOT EXISTS stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT,
                    total_messages INTEGER DEFAULT 0,
                    ai_replies INTEGER DEFAULT 0,
                    human_replies INTEGER DEFAULT 0,
                    platform TEXT
                );
            """)
            await db.commit()

            # Sample orders যোগ করো
            await self._add_sample_orders(db)

    async def _add_sample_orders(self, db):
        sample_orders = [
            ("ORD-001", "cust_001", "রহিম সাহেব", "01712345678",
             json.dumps([{"name": "Phone Case", "qty": 2, "price": 250}]),
             500, "shipped", "TRK-12345", "ঢাকা", datetime.now().isoformat()),
            ("ORD-002", "cust_002", "করিম ভাই", "01812345678",
             json.dumps([{"name": "Power Bank", "qty": 1, "price": 1200}]),
             1200, "processing", None, "চট্টগ্রাম", datetime.now().isoformat()),
            ("ORD-003", "cust_003", "Kamal Ahmed", "01912345678",
             json.dumps([{"name": "SaaS Basic Plan", "qty": 1, "price": 999}]),
             999, "delivered", "TRK-67890", "Sylhet", datetime.now().isoformat()),
        ]
        for order in sample_orders:
            try:
                await db.execute("""
                    INSERT OR IGNORE INTO orders
                    (id, customer_id, customer_name, phone, items, total_amount,
                     status, tracking_number, address, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, order)
        await db.commit()
            except:
                pass

    # ─── Conversation Methods ─────────────────────────────────
    async def get_conversation(self, conversation_id: str) -> Optional[dict]:
        async with await self._get_db() as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM conversations WHERE id = ?",
                (conversation_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return None
                conv = dict(row)
                conv["history"] = await self._get_messages(db, conversation_id)
                return conv

    async def create_conversation(self, data: dict) -> dict:
        async with await self._get_db() as db:
            now = datetime.now().isoformat()
            await db.execute("""
                INSERT INTO conversations
                (id, customer_id, platform, phone, ai_enabled, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, 1, 'active', ?, ?)
            """, (data["id"], data["customer_id"], data["platform"],
                  data.get("phone"), now, now))
            await db.commit()
        return {**data, "ai_enabled": True, "history": [], "status": "active"}

    async def add_message(self, conversation_id: str, role: str, content: str,
                          intent: str = None, language: str = None,
                          agent_name: str = None):
        async with await self._get_db() as db:
            now = datetime.now().isoformat()
            await db.execute("""
                INSERT INTO messages
                (conversation_id, role, content, intent, language, agent_name, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (conversation_id, role, content, intent, language, agent_name, now))
            await db.execute("""
                UPDATE conversations SET updated_at = ? WHERE id = ?
            """, (now, conversation_id))
            await db.commit()

    async def add_pending_message(self, conversation_id: str, message: str):
        await self.add_message(conversation_id, "pending", message)

    async def toggle_ai(self, conversation_id: str, enabled: bool):
        async with await self._get_db() as db:
            await db.execute("""
                UPDATE conversations SET ai_enabled = ? WHERE id = ?
            """, (1 if enabled else 0, conversation_id))
            await db.commit()

    async def get_conversations(self, platform: str = None, limit: int = 50) -> list:
        async with await self._get_db() as db:
            db.row_factory = aiosqlite.Row
            if platform:
                async with db.execute("""
                    SELECT * FROM conversations WHERE platform = ?
                    ORDER BY updated_at DESC LIMIT ?
                """, (platform, limit)) as cursor:
                    rows = await cursor.fetchall()
            else:
                async with db.execute("""
                    SELECT * FROM conversations
                    ORDER BY updated_at DESC LIMIT ?
                """, (limit,)) as cursor:
                    rows = await cursor.fetchall()

            result = []
            for row in rows:
                conv = dict(row)
                # শেষ মেসেজ যোগ করো
                async with db.execute("""
                    SELECT content, role, timestamp FROM messages
                    WHERE conversation_id = ?
                    ORDER BY timestamp DESC LIMIT 1
                """, (conv["id"],)) as msg_cursor:
                    last_msg = await msg_cursor.fetchone()
                    if last_msg:
                        conv["last_message"] = dict(last_msg)
                result.append(conv)
            return result

    async def _get_messages(self, db, conversation_id: str) -> list:
        async with db.execute("""
            SELECT role, content, intent, language, timestamp
            FROM messages WHERE conversation_id = ?
            ORDER BY timestamp ASC
        """, (conversation_id,)) as cursor:
            rows = await cursor.fetchall()
            messages = []
            # user + assistant pair বানাও
            temp_user = None
            for row in rows:
                role, content, intent, language, ts = row
                if role == "user":
                    temp_user = content
                elif role == "assistant" and temp_user:
                    messages.append({
                        "user": temp_user,
                        "assistant": content,
                        "intent": intent,
                        "language": language,
                        "timestamp": ts
                    })
                    temp_user = None
            return messages

    # ─── Order Methods ────────────────────────────────────────
    async def get_order(self, order_id: str) -> Optional[dict]:
        async with await self._get_db() as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM orders WHERE id = ?", (order_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return None
                order = dict(row)
                order["items"] = json.loads(order["items"] or "[]")
                return order

    # ─── Dashboard Stats ──────────────────────────────────────
    async def get_dashboard_stats(self) -> dict:
        async with await self._get_db() as db:
            stats = {}

            async with db.execute(
                "SELECT COUNT(*) FROM conversations"
            ) as c:
                stats["total_conversations"] = (await c.fetchone())[0]

            async with db.execute(
                "SELECT COUNT(*) FROM conversations WHERE status = 'active'"
            ) as c:
                stats["active_conversations"] = (await c.fetchone())[0]

            async with db.execute(
                "SELECT COUNT(*) FROM messages WHERE role = 'assistant'"
            ) as c:
                stats["ai_replies"] = (await c.fetchone())[0]

            async with db.execute(
                "SELECT COUNT(*) FROM messages WHERE role = 'agent'"
            ) as c:
                stats["human_replies"] = (await c.fetchone())[0]

            async with db.execute(
                "SELECT COUNT(*) FROM messages WHERE role = 'pending'"
            ) as c:
                stats["pending_messages"] = (await c.fetchone())[0]

            async with db.execute(
                "SELECT COUNT(*) FROM orders"
            ) as c:
                stats["total_orders"] = (await c.fetchone())[0]

            # Platform breakdown
            async with db.execute("""
                SELECT platform, COUNT(*) as count
                FROM conversations GROUP BY platform
            """) as c:
                rows = await c.fetchall()
                stats["by_platform"] = {row[0]: row[1] for row in rows}

            stats["timestamp"] = datetime.now().isoformat()
            return stats
