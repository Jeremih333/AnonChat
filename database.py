from datetime import datetime
from sqsnip import database as db_lib

class Database:
    def __init__(self, db_name: str):
        self.users_db = db_lib(
            db_name,
            "users",
            columns=[
                "id INTEGER PRIMARY KEY",
                "status INTEGER DEFAULT 0",
                "rid INTEGER DEFAULT 0",
                "gender TEXT",
                "age INTEGER",
                "vip INTEGER DEFAULT 0",
                "referral_count INTEGER DEFAULT 0",
                "referrer_id INTEGER",
                "vip_expiry DATETIME"
            ]
        )
        self._create_tables()
        self._create_indexes()

    def _create_tables(self):
        self.users_db.execute("""
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

    def _create_indexes(self):
        self.users_db.execute("""
            CREATE INDEX IF NOT EXISTS idx_status 
            ON users(status)
        """)
        self.users_db.execute("""
            CREATE INDEX IF NOT EXISTS idx_vip 
            ON users(vip, vip_expiry)
        """)

    def get_user_cursor(self, user_id: int) -> dict:
        result = self.users_db.select(
            columns="*",
            conditions={"id": user_id},
            fetch_all=False
        )
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

    def new_user(self, user_id: int):
        self.users_db.insert([user_id, 0, 0, None, None, 0, 0, None, None])

    def update_status(self, user_id: int, status: int):
        self.users_db.update(
            updates={"status": status},
            conditions={"id": user_id}
        )

    def search(self, user_id: int):
        self.update_status(user_id, 1)
        result = self.users_db.select(
            columns="*",
            conditions={"status": 1, "id": ("!=", user_id)},
            fetch_all=True
        )
        return self._format_search_result(result)

    def search_vip(self, user_id: int, gender: str):
        result = self.users_db.select(
            columns="*",
            conditions={
                "status": 1,
                "id": ("!=", user_id),
                "gender": gender
            },
            order_by="RANDOM()",
            limit=1,
            fetch_all=False
        )
        return self._format_search_result([result] if result else None)

    def _format_search_result(self, result):
        if not result:
            return None
        return {
            "id": result[0][0],
            "status": result[0][1],
            "rid": result[0][2],
            "gender": result[0][3],
            "age": result[0][4]
        }

    def start_chat(self, user_id: int, rival_id: int):
        with self.users_db.transaction():
            self.users_db.update(
                updates={"status": 2, "rid": rival_id},
                conditions={"id": user_id}
            )
            self.users_db.update(
                updates={"status": 2, "rid": user_id},
                conditions={"id": rival_id}
            )

    def stop_chat(self, user_id: int, rival_id: int):
        with self.users_db.transaction():
            self.users_db.update(
                updates={"status": 0, "rid": 0},
                conditions={"id": user_id}
            )
            self.users_db.update(
                updates={"status": 0, "rid": 0},
                conditions={"id": rival_id}
            )

    def update_gender_age(self, user_id: int, gender: str = None, age: int = None):
        updates = {}
        if gender:
            updates["gender"] = gender
        if age is not None:
            updates["age"] = age
        self.users_db.update(updates, {"id": user_id})

    def increment_referral_count(self, user_id: int):
        self.users_db.update(
            updates={"referral_count": ("+", 1)},
            conditions={"id": user_id}
        )

    def activate_vip(self, user_id: int, expiry_date: datetime):
        self.users_db.update(
            updates={
                "vip": 1,
                "vip_expiry": expiry_date.isoformat()
            },
            conditions={"id": user_id}
        )

    def check_vip_status(self, user_id: int) -> bool:
        user = self.get_user_cursor(user_id)
        if not user:
            return False
        return user['vip'] and user['vip_expiry'] > datetime.now()

    def close(self):
        self.users_db.close()
