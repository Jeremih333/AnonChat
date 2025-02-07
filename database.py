import sqlite3
from datetime import datetime
from sqsnip import database as db

class Database:
    def __init__(self, db_name: str):
        self.users_db = db(
            db_name, 
            "users",
            """
                id INTEGER PRIMARY KEY,
                status INTEGER DEFAULT 0,
                rid INTEGER DEFAULT 0,
                gender TEXT,
                age INTEGER,
                vip INTEGER DEFAULT 0,
                referral_count INTEGER DEFAULT 0,
                referrer_id INTEGER,
                vip_expiry DATETIME
            """
        )
        self._create_indexes()

    def _create_indexes(self):
        # Создание индексов для быстрого поиска
        self.users_db.execute("""
            CREATE INDEX IF NOT EXISTS idx_status 
            ON users(status)
        """)
        self.users_db.execute("""
            CREATE INDEX IF NOT EXISTS idx_vip 
            ON users(vip, vip_expiry)
        """)

    def get_user_cursor(self, user_id: int) -> dict:
        result = self.users_db.select("*", {"id": user_id}, False)
        if result:
            return {
                "id": result[0],
                "status": result[1],
                "rid": result[2],
                "gender": result[3],
                "age": result[4],
                "vip": result[5],
                "referral_count": result[6],
                "referrer_id": result[7],
                "vip_expiry": datetime.strptime(result[8], "%Y-%m-%d %H:%M:%S") if result[8] else None
            }
        return None

    def new_user(self, user_id: int):
        self.users_db.insert([user_id, 0, 0, None, None, 0, 0, None, None])

    def update_status(self, user_id: int, status: int):
        self.users_db.update({"status": status}, {"id": user_id})

    def search(self, user_id: int):
        self.update_status(user_id, 1)
        result = self.users_db.select(
            "*", 
            {"status": 1, "id": ("!=", user_id)}, 
            True
        )
        return self._format_result(result)

    def search_vip(self, user_id: int, gender: str):
        query = """
            SELECT * FROM users 
            WHERE status = 1 
            AND id != ? 
            AND gender = ?
            ORDER BY RANDOM() 
            LIMIT 1
        """
        result = self.users_db.execute(query, (user_id, gender)).fetchall()
        return self._format_result(result)

    def _format_result(self, result):
        return {
            "id": result[0][0],
            "status": result[0][1],
            "rid": result[0][2],
            "gender": result[0][3],
            "age": result[0][4]
        } if result else None

    def start_chat(self, user_id: int, rival_id: int):
        with self.users_db.conn:
            self.users_db.update({"status": 2, "rid": rival_id}, {"id": user_id})
            self.users_db.update({"status": 2, "rid": user_id}, {"id": rival_id})

    def stop_chat(self, user_id: int, rival_id: int):
        with self.users_db.conn:
            self.users_db.update({"status": 0, "rid": 0}, {"id": user_id})
            self.users_db.update({"status": 0, "rid": 0}, {"id": rival_id})

    def update_gender_age(self, user_id: int, gender: str = None, age: int = None):
        updates = {}
        if gender: updates["gender"] = gender
        if age: updates["age"] = age
        self.users_db.update(updates, {"id": user_id})

    def increment_referral_count(self, user_id: int):
        self.users_db.execute(
            "UPDATE users SET referral_count = referral_count + 1 WHERE id = ?",
            (user_id,)
        )

    def activate_vip(self, user_id: int, expiry_date: datetime):
        self.users_db.update(
            {
                "vip": 1,
                "vip_expiry": expiry_date.strftime("%Y-%m-%d %H:%M:%S")
            },
            {"id": user_id}
        )

    def check_vip_status(self, user_id: int) -> bool:
        user = self.get_user_cursor(user_id)
        return user and user['vip'] and user['vip_expiry'] > datetime.now()

    def close(self):
        self.users_db.close()
