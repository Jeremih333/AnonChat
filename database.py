import asyncio
import aiosqlite
from datetime import datetime

class Database:
    def __init__(self, db_name: str):
        self.db_name = db_name
        # Исправлено: безопасный запуск асинхронной задачи
        try:
            asyncio.get_event_loop().run_until_complete(self._create_tables())
        except RuntimeError:
            asyncio.new_event_loop().run_until_complete(self._create_tables())

    async def _create_tables(self):
        async with aiosqlite.connect(self.db_name) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY,
                    status INTEGER DEFAULT 0,
                    rid INTEGER DEFAULT 0,
                    gender TEXT,
                    age INTEGER,
                    vip INTEGER DEFAULT 0,
                    referral_count INTEGER DEFAULT 0,
                    referrer_id INTEGER,
                    vip_expiry DATETIME
                )
            """)
            await db.commit()

    async def get_user_cursor(self, user_id: int) -> dict:
        async with aiosqlite.connect(self.db_name) as db:
            async with db.execute("SELECT * FROM users WHERE id = ?", (user_id,)) as cursor:
                result = await cursor.fetchone()
                return self._format_user(result) if result else None

    def _format_user(self, result):
        return {
            "id": result[0],
            "status": result[1],
            "rid": result[2],
            "gender": result[3],
            "age": result[4],
            "vip": result[5],
            "referral_count": result[6],
            "referrer_id": result[7],
            "vip_expiry": datetime.fromisoformat(result[8]) if result[8] else None
        }

    async def new_user(self, user_id: int):
        async with aiosqlite.connect(self.db_name) as db:
            await db.execute("INSERT OR IGNORE INTO users (id) VALUES (?)", (user_id,))
            await db.commit()

    async def update_status(self, user_id: int, status: int):
        async with aiosqlite.connect(self.db_name) as db:
            await db.execute("UPDATE users SET status = ? WHERE id = ?", (status, user_id))
            await db.commit()

    async def search(self, user_id: int):
        await self.update_status(user_id, 1)
        async with aiosqlite.connect(self.db_name) as db:
            async with db.execute("""
                SELECT * FROM users 
                WHERE status = 1 AND id != ? 
                ORDER BY RANDOM() LIMIT 1
            """, (user_id,)) as cursor:
                result = await cursor.fetchone()
                return self._format_search_result(result)

    async def search_vip(self, user_id: int, gender: str):
        async with aiosqlite.connect(self.db_name) as db:
            async with db.execute("""
                SELECT * FROM users 
                WHERE status = 1 AND id != ? AND gender = ?
                ORDER BY RANDOM() LIMIT 1
            """, (user_id, gender)) as cursor:
                result = await cursor.fetchone()
                return self._format_search_result(result)

    def _format_search_result(self, result):
        if not result:
            return None
        return {
            "id": result[0],
            "status": result[1],
            "rid": result[2],
            "gender": result[3],
            "age": result[4]
        }

    async def start_chat(self, user_id: int, rival_id: int):
        async with aiosqlite.connect(self.db_name) as db:
            await db.execute("BEGIN TRANSACTION")
            try:
                await db.execute(
                    "UPDATE users SET status = 2, rid = ? WHERE id = ?", 
                    (rival_id, user_id)
                )
                await db.execute(
                    "UPDATE users SET status = 2, rid = ? WHERE id = ?", 
                    (user_id, rival_id)
                )
                await db.commit()
            except Exception as e:
                await db.rollback()
                raise e

    async def stop_chat(self, user_id: int, rival_id: int):
        async with aiosqlite.connect(self.db_name) as db:
            await db.execute("BEGIN TRANSACTION")
            try:
                await db.execute(
                    "UPDATE users SET status = 0, rid = 0 WHERE id = ?", 
                    (user_id,)
                )
                await db.execute(
                    "UPDATE users SET status = 0, rid = 0 WHERE id = ?", 
                    (rival_id,)
                )
                await db.commit()
            except Exception as e:
                await db.rollback()
                raise e

    async def update_gender_age(self, user_id: int, gender: str = None, age: int = None):
        updates = []
        params = []
        if gender:
            updates.append("gender = ?")
            params.append(gender)
        if age is not None:
            updates.append("age = ?")
            params.append(age)
        params.append(user_id)

        if updates:
            async with aiosqlite.connect(self.db_name) as db:
                await db.execute(
                    f"UPDATE users SET {', '.join(updates)} WHERE id = ?",
                    params
                )
                await db.commit()

    async def increment_referral_count(self, user_id: int):
        async with aiosqlite.connect(self.db_name) as db:
            await db.execute(
                "UPDATE users SET referral_count = referral_count + 1 WHERE id = ?", 
                (user_id,)
            )
            await db.commit()

    async def activate_vip(self, user_id: int, expiry_date: datetime):
        async with aiosqlite.connect(self.db_name) as db:
            await db.execute(
                "UPDATE users SET vip = 1, vip_expiry = ? WHERE id = ?", 
                (expiry_date.isoformat(), user_id)
            )
            await db.commit()

    async def check_vip_status(self, user_id: int) -> bool:
        user = await self.get_user_cursor(user_id)
        if not user:
            return False
        if user['vip_expiry'] and datetime.now() > user['vip_expiry']:
            await self.deactivate_vip(user_id)
            return False
        return user['vip'] == 1

    async def deactivate_vip(self, user_id: int):
        async with aiosqlite.connect(self.db_name) as db:
            await db.execute(
                "UPDATE users SET vip = 0, vip_expiry = NULL WHERE id = ?",
                (user_id,)
            )
            await db.commit()
