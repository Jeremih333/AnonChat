import sqlite3
from typing import Optional, List, Dict

class Database:
    def __init__(self, db_name: str = "users.db"):
        self.conn = sqlite3.connect(db_name, check_same_thread=False)
        self.cursor = self.conn.cursor()
        
        # Создаем таблицы при инициализации
        self._create_tables()

    def _create_tables(self):
        """Создает необходимые таблицы в базе данных"""
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER UNIQUE NOT NULL,
                status INTEGER DEFAULT 0,
                rid INTEGER DEFAULT 0
            )
        """)
        
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS message_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                rival_message_id INTEGER NOT NULL,
                UNIQUE(user_id, message_id)
            )
        """)
        self.conn.commit()

    def get_user(self, user_id: int) -> Optional[Dict]:
        """Получает информацию о пользователе"""
        self.cursor.execute(
            "SELECT user_id, status, rid FROM users WHERE user_id = ?",
            (user_id,)
        )
        result = self.cursor.fetchone()
        if result:
            return {
                "user_id": result[0],
                "status": result[1],
                "rid": result[2]
            }
        return None

    def get_users_in_search(self) -> int:
        """Возвращает количество пользователей в поиске"""
        self.cursor.execute(
            "SELECT COUNT(*) FROM users WHERE status = 1"
        )
        return self.cursor.fetchone()[0]

    def new_user(self, user_id: int):
        """Добавляет нового пользователя"""
        try:
            self.cursor.execute(
                "INSERT INTO users (user_id) VALUES (?)",
                (user_id,)
            )
            self.conn.commit()
        except sqlite3.IntegrityError:
            pass  # Пользователь уже существует

    def search(self, user_id: int) -> Optional[Dict]:
        """Начинает поиск собеседника и возвращает найденного"""
        # Обновляем статус текущего пользователя
        self.cursor.execute(
            "UPDATE users SET status = 1, rid = 0 WHERE user_id = ?",
            (user_id,)
        )
        
        # Ищем кандидатов
        self.cursor.execute(
            "SELECT user_id, status, rid FROM users "
            "WHERE status = 1 AND user_id != ? "
            "ORDER BY RANDOM() LIMIT 1",
            (user_id,)
        )
        rival = self.cursor.fetchone()
        
        if not rival:
            return None
        
        return {
            "user_id": rival[0],
            "status": rival[1],
            "rid": rival[2]
        }

    def start_chat(self, user_id: int, rival_id: int):
        """Начинает чат между двумя пользователями"""
        with self.conn:
            self.cursor.execute(
                "UPDATE users SET status = 2, rid = ? WHERE user_id = ?",
                (rival_id, user_id)
            )
            self.cursor.execute(
                "UPDATE users SET status = 2, rid = ? WHERE user_id = ?",
                (user_id, rival_id)
            )

    def stop_chat(self, user_id: int, rival_id: int):
        """Завершает чат между пользователями"""
        with self.conn:
            self.cursor.execute(
                "UPDATE users SET status = 0, rid = 0 WHERE user_id = ?",
                (user_id,)
            )
            self.cursor.execute(
                "UPDATE users SET status = 0, rid = 0 WHERE user_id = ?",
                (rival_id,)
            )

    def stop_search(self, user_id: int):
        """Останавливает поиск собеседника"""
        self.cursor.execute(
            "UPDATE users SET status = 0, rid = 0 WHERE user_id = ?",
            (user_id,)
        )
        self.conn.commit()

    def save_message_link(self, user_id: int, message_id: int, rival_message_id: int):
        """Сохраняет связь между сообщениями"""
        self.cursor.execute(
            "INSERT INTO message_links (user_id, message_id, rival_message_id) "
            "VALUES (?, ?, ?)",
            (user_id, message_id, rival_message_id)
        )
        self.conn.commit()

    def get_rival_message_id(self, user_id: int, message_id: int) -> Optional[int]:
        """Возвращает связанный ID сообщения"""
        self.cursor.execute(
            "SELECT rival_message_id FROM message_links "
            "WHERE user_id = ? AND message_id = ?",
            (user_id, message_id)
        )
        result = self.cursor.fetchone()
        return result[0] if result else None

    def close(self):
        """Закрывает соединение с базой данных"""
        self.conn.close()
