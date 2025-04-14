import sqlite3
from sqsnip import database as db

class database:
    def __init__(self, db_name: str):
        # Инициализация таблицы пользователей
        self.users_db = db(
            db_name, 
            "users",
            """
                id INTEGER PRIMARY KEY,
                status INTEGER DEFAULT 0,
                rid INTEGER DEFAULT 0,
                interests TEXT DEFAULT ''
            """
        )

        # Инициализация таблицы связей сообщений
        self.messages_db = db(
            db_name,
            "message_links",
            """
                user_id INTEGER,
                message_id INTEGER,
                rival_message_id INTEGER,
                PRIMARY KEY(user_id, message_id)
            """
        )

    def get_user_cursor(self, user_id: int) -> dict:
        result = self.users_db.select("*", {"id": user_id}, False)
        return {
            "status": result[1],
            "rid": result[2],
            "interests": result[3]
        } if result else None

    def get_users_in_search(self) -> int:
        result = self.users_db.select("*", {"status": 1}, True)
        return len(result) if result else 0

    def new_user(self, user_id: int):
        self.users_db.insert([user_id, 0, 0, ''])

    def search(self, user_id: int):
        self.users_db.update({"rid": 0, "status": 1}, {"id": user_id})
        result = self.users_db.select("*", {"status": 1}, True)

        if not result:
            return None

        candidates = [row for row in result if row[0] != user_id]
        if not candidates:
            return None

        rival = candidates[0]
        return {
            "id": rival[0],
            "status": rival[1],
            "rid": rival[2],
            "interests": rival[3]
        }

    # Методы для работы с интересами
    def get_user_interests(self, user_id: int) -> list:
        result = self.users_db.select("interests", {"id": user_id}, False)
        return result[0].split(',') if result and result[0] else []

    def add_interest(self, user_id: int, interest: str):
        current = self.get_user_interests(user_id)
        if interest not in current:
            current.append(interest)
            self.users_db.update(
                {"interests": ','.join(current)}, 
                {"id": user_id}
            )

    def remove_interest(self, user_id: int, interest: str):
        current = self.get_user_interests(user_id)
        if interest in current:
            current.remove(interest)
            new_interests = ','.join(current) if current else ''
            self.users_db.update(
                {"interests": new_interests}, 
                {"id": user_id}
            )

    def clear_interests(self, user_id: int):
        self.users_db.update({"interests": ''}, {"id": user_id})

    # Остальные методы остаются без изменений
    def start_chat(self, user_id: int, rival_id: int):
        self.users_db.update({"status": 2, "rid": rival_id}, {"id": user_id})
        self.users_db.update({"status": 2, "rid": user_id}, {"id": rival_id})

    def stop_chat(self, user_id: int, rival_id: int):
        self.users_db.update({"status": 0, "rid": 0}, {"id": user_id})
        self.users_db.update({"status": 0, "rid": 0}, {"id": rival_id})

    def stop_search(self, user_id: int):
        self.users_db.update({"status": 0, "rid": 0}, {"id": user_id})

    def save_message_link(self, user_id: int, message_id: int, rival_message_id: int):
        self.messages_db.insert([user_id, message_id, rival_message_id])

    def get_rival_message_id(self, user_id: int, message_id: int) -> int:
        result = self.messages_db.select(
            "rival_message_id", 
            {"user_id": user_id, "message_id": message_id}, 
            False
        )
        return result[0] if result else None

    def close(self):
        self.users_db.close()
        self.messages_db.close()
