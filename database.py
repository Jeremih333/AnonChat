import sqlite3
from typing import Optional, Dict

class database:  # Используем оригинальное имя класса как в импорте
    def __init__(self, db_name: str = "users.db"):
        self.conn = sqlite3.connect(db_name, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row  # Для доступа к полям по имени
        self.cursor = self.conn.cursor()
        
        self._create_tables()

    def _create_tables(self):
        """Создает таблицы в базе данных"""
        self.cursor.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                status INTEGER DEFAULT 0,
                rid INTEGER DEFAULT 0
            );
            
            CREATE TABLE IF NOT EXISTS message_links (
                user_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                rival_message_id INTEGER NOT NULL,
                PRIMARY KEY(user_id, message_id)
            );
        """)
        self.conn.commit()

    def get_user_cursor(self, user_id: int) -> Optional[Dict]:
        """Получает пользователя по ID (оригинальное имя метода)"""
        self.cursor.execute(
            "SELECT * FROM users WHERE user_id = ?",
            (user_id,)
        )
        result = self.cursor.fetchone()
        return dict(result) if result else None

    def get_users_in_search(self) -> int:
        """Количество пользователей в поиске"""
        self.cursor.execute("SELECT COUNT(*) FROM users WHERE status = 1")
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
            pass

    def search(self, user_id: int) -> Optional[Dict]:
        """Поиск собеседника"""
        # Обновляем статус текущего пользователя
        self.cursor.execute(
            "UPDATE users SET status = 1, rid = 0 WHERE user_id = ?",
            (user_id,)
        )
        
        # Ищем кандидата
        self.cursor.execute(
            "SELECT * FROM users WHERE status = 1 AND user_id != ? LIMIT 1",
            (user_id,)
        )
        rival = self.cursor.fetchone()
        return dict(rival) if rival else None

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
        """Завершает чат"""
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
        """Останавливает поиск"""
        self.cursor.execute(
            "UPDATE users SET status = 0, rid = 0 WHERE user_id = ?",
            (user_id,)
        )
        self.conn.commit()

    def save_message_link(self, user_id: int, message_id: int, rival_message_id: int):
        """Сохраняет связь сообщений"""
        self.cursor.execute(
            "INSERT INTO message_links VALUES (?, ?, ?)",
            (user_id, message_id, rival_message_id)
        )
        self.conn.commit()

    def get_rival_message_id(self, user_id: int, message_id: int) -> Optional[int]:
        """Получает связанное сообщение"""
        self.cursor.execute(
            "SELECT rival_message_id FROM message_links "
            "WHERE user_id = ? AND message_id = ?",
            (user_id, message_id)
        )
        result = self.cursor.fetchone()
        return result[0] if result else None

    def close(self):
        """Закрывает соединение"""
        self.conn.close()
