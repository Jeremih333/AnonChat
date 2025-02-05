import sqlite3
from typing import Optional, Dict

class database:
    def __init__(self, db_name: str = "users.db"):
        self.conn = sqlite3.connect(db_name, check_same_thread=False)
        self.cursor = self.conn.cursor()
        
        # Принудительно пересоздаем таблицы с новой структурой
        self._drop_tables()
        self._create_tables()

    def _drop_tables(self):
        """Удаляем старые таблицы для чистого обновления"""
        self.cursor.execute("DROP TABLE IF EXISTS users")
        self.cursor.execute("DROP TABLE IF EXISTS message_links")
        self.conn.commit()

    def _create_tables(self):
        """Создаем таблицы с правильной структурой"""
        self.cursor.executescript("""
            CREATE TABLE users (
                user_id INTEGER PRIMARY KEY,
                status INTEGER DEFAULT 0,
                rid INTEGER DEFAULT 0
            );
            
            CREATE TABLE message_links (
                user_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                rival_message_id INTEGER NOT NULL,
                PRIMARY KEY(user_id, message_id)
            );
        """)
        self.conn.commit()

    def get_user_cursor(self, user_id: int) -> Optional[Dict]:
        self.cursor.execute(
            "SELECT user_id, status, rid FROM users WHERE user_id = ?",
            (user_id,)
        )
        result = self.cursor.fetchone()
        return {
            "user_id": result[0],
            "status": result[1],
            "rid": result[2]
        } if result else None

    # Остальные методы остаются без изменений
    # ...

    def close(self):
        self.conn.close()

Найти еще
