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
        if not result:
            return None
        return {
            "id": result[0],
            "status": result[1],
            "rid": result[2],
            "interests": result[3]
        }

    def get_users_in_search(self) -> int:
        result = self.users_db.select("*", {"status": 1}, True)
        return len(result) if result else 0

    def new_user(self, user_id: int):
        self.users_db.insert([user_id, 0, 0, ''])

    def search(self, user_id: int):
        current_user = self.get_user_cursor(user_id)
        if not current_user:
            return None

        self.users_db.update({"rid": 0, "status": 1}, {"id": user_id})
        
        # Получаем интересы текущего пользователя
        user_interests = set(current_user['interests'].split(',')) if current_user['interests'] else set()
        
        # Ищем кандидатов с совпадающими интересами
        all_candidates = self.users_db.select("*", {"status": 1}, True)
        if not all_candidates:
            return None

        candidates = []
        for candidate in all_candidates:
            if candidate[0] == user_id:
                continue
            
            # Получаем интересы кандидата
            candidate_interests = set(candidate[3].split(',')) if candidate[3] else set()
            
            # Если есть пересечение интересов или интересы не указаны
            if not user_interests or user_interests & candidate_interests:
                candidates.append({
                    "id": candidate[0],
                    "status": candidate[1],
                    "rid": candidate[2],
                    "interests": candidate[3]
                })

        if not candidates:
            return None

        # Сортируем по количеству совпадений интересов
        candidates.sort(
            key=lambda x: len(user_interests & set(x['interests'].split(','))) if x['interests'] else 0,
            reverse=True
        )

        return candidates[0]

    # Методы для работы с интересами
    def get_user_interests(self, user_id: int) -> list:
        result = self.users_db.select("interests", {"id": user_id}, False)
        return result[0].split(',') if result and result[0] else []

    def add_interest(self, user_id: int, interest: str):
        current = self.get_user_interests(user_id)
        if interest not in current:
            current.append(interest)
            self._update_interests(user_id, current)

    def remove_interest(self, user_id: int, interest: str):
        current = self.get_user_interests(user_id)
        if interest in current:
            current.remove(interest)
            self._update_interests(user_id, current)

    def _update_interests(self, user_id: int, interests: list):
        new_interests = ','.join([i.strip() for i in interests if i.strip()])
        self.users_db.update(
            {"interests": new_interests}, 
            {"id": user_id}
        )

    def clear_interests(self, user_id: int):
        self.users_db.update({"interests": ''}, {"id": user_id})

    # Остальные методы
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
