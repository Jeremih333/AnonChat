import asyncio
import aiosqlite
from datetime import datetime

class Database:
    def __init__(self, db_name: str):
        self.db_name = db_name
        try:
            asyncio.get_event_loop().run_until_complete(self._create_tables())
        except RuntimeError:
            asyncio.new_event_loop().run_until_complete(self._create_tables())

    async def _create_tables(self):
        async with aiosqlite.connect(self.db_name) as db:
            # Создаем основную таблицу
            await db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY,
                    status INTEGER DEFAULT 0,
                    rid INTEGER DEFAULT 0,
                    vip INTEGER DEFAULT 0,
                    referral_count INTEGER DEFAULT 0,
                    referrer_id INTEGER DEFAULT 0,
                    vip_expiry DATETIME DEFAULT NULL
                )
            """)
            
            # Проверяем и добавляем новые столбцы
            columns_to_add = [
                ('gender', 'TEXT DEFAULT ""'),
                ('age', 'INTEGER DEFAULT 0')
            ]
            
            # Получаем информацию о существующих столбцах
            async with db.execute("PRAGMA table_info(users)") as cursor:
                existing_columns = [row[1] for row in await cursor.fetchall()]
            
            # Добавляем недостающие столбцы
            for column, definition in columns_to_add:
                if column not in existing_columns:
                    await db.execute(f"ALTER TABLE users ADD COLUMN {column} {definition}")
            
            await db.commit()

    async def get_user_cursor(self, user_id: int) -> dict:
        async with aiosqlite.connect(self.db_name) as db:
            async with db.execute("SELECT * FROM users WHERE id = ?", (user_id,)) as cursor:
                result = await cursor.fetchone()
                return self._format_user(result) if result else None

    def _format_user(self, result):
        return {
            "id": result[0],
            "status": result[1] if len(result) > 1 else 0,
            "rid": result[2] if len(result) > 2 else 0,
            "vip": result[3] if len(result) > 3 else 0,
            "referral_count": result[4] if len(result) > 4 else 0,
            "referrer_id": result[5] if len(result) > 5 else 0,
            "vip_expiry": datetime.fromisoformat(result[6]) if len(result) > 6 and result[6] else None,
            "gender": result[7] if len(result) > 7 else '',
            "age": result[8] if len(result) > 8 else 0
        }

    async def new_user(self, user_id: int):
        async with aiosqlite.connect(self.db_name) as db:
            await db.execute("""
                INSERT INTO users (id) 
                VALUES (?)
                ON CONFLICT(id) DO NOTHING
            """, (user_id,))
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
            "gender": result[7] if len(result) > 7 else '',
            "age": result[8] if len(result) > 8 else 0
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
