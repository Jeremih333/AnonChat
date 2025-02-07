import asyncio
import aiosqlite
from datetime import datetime
from dataclasses import dataclass

@dataclass
class User:
    id: int
    gender: str = ''
    age: int = 0
    status: int = 0
    rid: int = 0
    vip: int = 0
    referral_count: int = 0
    referrer_id: int = 0
    vip_expiry: datetime = None

class Database:
    def __init__(self, db_name: str):
        self.db_name = db_name
        asyncio.run(self._create_tables())

    async def _create_tables(self):
        async with aiosqlite.connect(self.db_name) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY,
                    gender TEXT DEFAULT '',
                    age INTEGER DEFAULT 0,
                    status INTEGER DEFAULT 0,
                    rid INTEGER DEFAULT 0,
                    vip INTEGER DEFAULT 0,
                    referral_count INTEGER DEFAULT 0,
                    referrer_id INTEGER DEFAULT 0,
                    vip_expiry DATETIME DEFAULT NULL
                )
            """)
            await db.commit()

    async def get_user(self, user_id: int) -> User:
        async with aiosqlite.connect(self.db_name) as db:
            async with db.execute("SELECT * FROM users WHERE id = ?", (user_id,)) as cursor:
                row = await cursor.fetchone()
                return User(*row) if row else None

    async def new_user(self, user_id: int):
        async with aiosqlite.connect(self.db_name) as db:
            await db.execute("""
                INSERT INTO users (id) VALUES (?)
                ON CONFLICT(id) DO NOTHING
            """, (user_id,))
            await db.commit()

    async def update_user(self, user_id: int, **kwargs):
        updates = []
        params = []
        for key, value in kwargs.items():
            updates.append(f"{key} = ?")
            params.append(value)
        params.append(user_id)

        async with aiosqlite.connect(self.db_name) as db:
            await db.execute(
                f"UPDATE users SET {', '.join(updates)} WHERE id = ?",
                params
            )
            await db.commit()

    async def search(self, user_id: int) -> User:
        await self.update_user(user_id, status=1)
        async with aiosqlite.connect(self.db_name) as db:
            async with db.execute("""
                SELECT * FROM users 
                WHERE status = 1 
                AND id != ? 
                ORDER BY RANDOM() LIMIT 1
            """, (user_id,)) as cursor:
                row = await cursor.fetchone()
                return User(*row) if row else None

    async def search_vip(self, user_id: int, gender: str) -> User:
        async with aiosqlite.connect(self.db_name) as db:
            async with db.execute("""
                SELECT * FROM users 
                WHERE status = 1 
                AND id != ? 
                AND gender = ?
                AND vip = 1
                AND vip_expiry > datetime('now')
                ORDER BY RANDOM() LIMIT 1
            """, (user_id, gender)) as cursor:
                row = await cursor.fetchone()
                return User(*row) if row else None

    async def start_chat(self, user_id: int, rival_id: int) -> bool:
        async with aiosqlite.connect(self.db_name) as db:
            await db.execute("BEGIN TRANSACTION")
            try:
                user = await self.get_user(user_id)
                rival = await self.get_user(rival_id)
                
                if user.status != 1 or rival.status != 1:
                    return False
                
                await self.update_user(user_id, status=2, rid=rival_id)
                await self.update_user(rival_id, status=2, rid=user_id)
                await db.commit()
                return True
            except Exception as e:
                await db.rollback()
                print(f"Ошибка начала чата: {e}")
                return False

    async def stop_chat(self, user_id: int, rival_id: int):
        async with aiosqlite.connect(self.db_name) as db:
            await db.execute("BEGIN TRANSACTION")
            try:
                await self.update_user(user_id, status=0, rid=0)
                await self.update_user(rival_id, status=0, rid=0)
                await db.commit()
            except Exception as e:
                await db.rollback()
                raise e

    async def increment_referral_count(self, user_id: int):
        async with aiosqlite.connect(self.db_name) as db:
            await db.execute(
                "UPDATE users SET referral_count = referral_count + 1 WHERE id = ?", 
                (user_id,)
            )
            await db.commit()

    async def activate_vip(self, user_id: int, expiry_date: datetime):
        await self.update_user(
            user_id, 
            vip=1, 
            vip_expiry=expiry_date.strftime("%Y-%m-%d %H:%M:%S")
        )

    async def check_vip_status(self, user_id: int) -> bool:
        user = await self.get_user(user_id)
        if not user or not user.vip:
            return False
            
        if user.vip_expiry and datetime.now() > user.vip_expiry:
            await self.deactivate_vip(user_id)
            return False
            
        return True

    async def deactivate_vip(self, user_id: int):
        await self.update_user(
            user_id, 
            vip=0, 
            vip_expiry=None
        )
