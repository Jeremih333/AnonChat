import sqlite3

class Database:
    def __init__(self, db_name: str):
        self.conn = sqlite3.connect(db_name)
        self.cursor = self.conn.cursor()
        self._init_db()

    def _init_db(self):
        # Создаем таблицу пользователей
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS users (
                            id INTEGER PRIMARY KEY,
                            searching INTEGER DEFAULT 0
                            )''')
                            
        # Создаем таблицу чатов
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS chats (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            user1 INTEGER,
                            user2 INTEGER,
                            FOREIGN KEY(user1) REFERENCES users(id),
                            FOREIGN KEY(user2) REFERENCES users(id)
                            )''')
        self.conn.commit()

    def add_user(self, user_id: int):
        self.cursor.execute("INSERT OR IGNORE INTO users (id) VALUES (?)", (user_id,))
        self.conn.commit()

    def get_user(self, user_id: int) -> dict:
        self.cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        result = self.cursor.fetchone()
        return {'id': result[0], 'searching': result[1]} if result else None

    def update_user(self, user_id: int, data: dict):
        set_clause = ', '.join([f"{k} = ?" for k in data])
        values = list(data.values()) + [user_id]
        self.cursor.execute(f"UPDATE users SET {set_clause} WHERE id = ?", values)
        self.conn.commit()

    def find_rival(self, user_id: int) -> int:
        # Ищем пользователя в поиске
        self.cursor.execute('''SELECT id FROM users 
                            WHERE searching = 1 AND id != ? 
                            LIMIT 1''', (user_id,))
        result = self.cursor.fetchone()
        if result:
            rival_id = result[0]
            self.update_user(rival_id, {'searching': 0})
            self.update_user(user_id, {'searching': 0})
            return rival_id
        return None

    def create_chat(self, user1: int, user2: int):
        self.cursor.execute("INSERT INTO chats (user1, user2) VALUES (?, ?)", (user1, user2))
        self.conn.commit()

    def get_chat(self, user_id: int) -> dict:
        self.cursor.execute('''SELECT * FROM chats 
                            WHERE user1 = ? OR user2 = ?''', (user_id, user_id))
        result = self.cursor.fetchone()
        return {'id': result[0], 'user1': result[1], 'user2': result[2]} if result else None

    def delete_chat(self, chat_id: int):
        self.cursor.execute("DELETE FROM chats WHERE id = ?", (chat_id,))
        self.conn.commit()
