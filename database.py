import sqlite3
from typing import Optional, Dict, List

class Database:
    def __init__(self, db_name: str):
        self.conn = sqlite3.connect(db_name)
        self.cursor = self.conn.cursor()
        self._create_tables()
        self._migrate_database()

    def _create_tables(self):
        """Создание таблиц с актуальной структурой"""
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                status INTEGER DEFAULT 0,
                rid INTEGER,
                interests TEXT DEFAULT '',
                age INTEGER,
                gender TEXT,
                referrer_id INTEGER,
                invited_count INTEGER DEFAULT 0
            )
        """)
        
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS message_links (
                user_id INTEGER,
                message_id INTEGER,
                rival_message_id INTEGER,
                PRIMARY KEY(user_id, message_id)
            )
        """)
        self.conn.commit()

    def _migrate_database(self):
        """Миграции для существующих баз данных"""
        try:
            self.cursor.execute("PRAGMA table_info(users)")
            columns = [column[1] for column in self.cursor.fetchall()]
            
            # Список необходимых миграций
            migrations = {
                'age': 'INTEGER',
                'gender': 'TEXT',
                'referrer_id': 'INTEGER',
                'invited_count': 'INTEGER DEFAULT 0'
            }
            
            for column, data_type in migrations.items():
                if column not in columns:
                    self.cursor.execute(f"""
                        ALTER TABLE users 
                        ADD COLUMN {column} {data_type}
                    """)
            self.conn.commit()
        except sqlite3.Error as e:
            print(f"Migration error: {e}")

    def get_user(self, user_id: int) -> Optional[Dict]:
        """Получение полной информации о пользователе"""
        try:
            self.cursor.execute(
                """SELECT id, status, rid, interests, 
                   age, gender, referrer_id, invited_count 
                   FROM users WHERE id = ?""",
                (user_id,)
            )
            result = self.cursor.fetchone()
            if result:
                return {
                    "id": result[0],
                    "status": result[1],
                    "rid": result[2],
                    "interests": result[3] or '',
                    "age": result[4],
                    "gender": result[5],
                    "referrer_id": result[6],
                    "invited_count": result[7] or 0
                }
            return None
        except sqlite3.OperationalError as e:
            if "no such column" in str(e):
                self._migrate_database()
                return self.get_user(user_id)
            raise

    def new_user(self, user_id: int, referrer_id: int = None):
        """Добавляет нового пользователя с реферером"""
        with self.conn:
            self.cursor.execute(
                "INSERT OR IGNORE INTO users (id) VALUES (?)",
                (user_id,)
            )
            if referrer_id:
                self.cursor.execute(
                    "UPDATE users SET referrer_id = ? WHERE id = ?",
                    (referrer_id, user_id)
                )
                self.cursor.execute(
                    "UPDATE users SET invited_count = invited_count + 1 WHERE id = ?",
                    (referrer_id,)
                )

    def update_age_gender(self, user_id: int, age: int, gender: str):
        """Обновляет возраст и пол пользователя"""
        with self.conn:
            self.cursor.execute(
                "UPDATE users SET age = ?, gender = ? WHERE id = ?",
                (age, gender, user_id)
            )

    def search(self, user_id: int, gender_filter: str = None) -> Optional[Dict]:
        """Поиск собеседника с учетом фильтров"""
        query = """
            SELECT id, interests, gender 
            FROM users 
            WHERE status = 1 AND id != ?
        """
        params = [user_id]
        
        if gender_filter:
            query += " AND gender = ?"
            params.append(gender_filter)
            
        query += " ORDER BY RANDOM() LIMIT 1"
        
        self.cursor.execute(query, params)
        candidate = self.cursor.fetchone()
        
        return {
            "id": candidate[0],
            "interests": candidate[1].split(',') if candidate[1] else [],
            "gender": candidate[2]
        } if candidate else None

    def start_chat(self, user1: int, user2: int):
        """Начинает чат между пользователями"""
        with self.conn:
            self.cursor.execute(
                "UPDATE users SET status = 2, rid = ? WHERE id = ?",
                (user2, user1)
            )
            self.cursor.execute(
                "UPDATE users SET status = 2, rid = ? WHERE id = ?",
                (user1, user2)
            )

    def stop_chat(self, user1: int, user2: int):
        """Завершает чат между пользователями"""
        with self.conn:
            self.cursor.execute(
                "UPDATE users SET status = 0, rid = NULL WHERE id = ?",
                (user1,)
            )
            self.cursor.execute(
                "UPDATE users SET status = 0, rid = NULL WHERE id = ?",
                (user2,)
            )

    def get_referral_info(self, user_id: int) -> Dict:
        """Возвращает реферальную статистику"""
        self.cursor.execute(
            "SELECT invited_count, referrer_id FROM users WHERE id = ?",
            (user_id,)
        )
        result = self.cursor.fetchone()
        return {
            "invited_count": result[0] if result else 0,
            "referrer_id": result[1] if result else None
        }

    def save_message_link(self, user_id: int, message_id: int, rival_message_id: int):
        """Сохраняет связь между сообщениями"""
        with self.conn:
            self.cursor.execute(
                "INSERT INTO message_links VALUES (?, ?, ?)",
                (user_id, message_id, rival_message_id)
            )

    def get_rival_message_id(self, user_id: int, message_id: int) -> Optional[int]:
        """Получает ID связанного сообщения"""
        self.cursor.execute(
            "SELECT rival_message_id FROM message_links WHERE user_id = ? AND message_id = ?",
            (user_id, message_id)
        )
        result = self.cursor.fetchone()
        return result[0] if result else None

    def add_interest(self, user_id: int, interest: str):
        """Добавляет интерес пользователю"""
        interests = self.get_user_interests(user_id)
        if interest not in interests:
            interests.append(interest)
            self._update_interests(user_id, interests)

    def remove_interest(self, user_id: int, interest: str):
        """Удаляет интерес у пользователя"""
        interests = self.get_user_interests(user_id)
        if interest in interests:
            interests.remove(interest)
            self._update_interests(user_id, interests)

    def get_user_interests(self, user_id: int) -> List[str]:
        """Возвращает список интересов пользователя"""
        self.cursor.execute(
            "SELECT interests FROM users WHERE id = ?",
            (user_id,)
        )
        result = self.cursor.fetchone()
        return result[0].split(',') if result and result[0] else []

    def _update_interests(self, user_id: int, interests: list):
        """Обновляет интересы в базе"""
        with self.conn:
            self.cursor.execute(
                "UPDATE users SET interests = ? WHERE id = ?",
                (','.join(filter(None, interests)), user_id)
            )

    def stop_search(self, user_id: int):
        """Останавливает поиск"""
        with self.conn:
            self.cursor.execute(
                "UPDATE users SET status = 0, rid = 0 WHERE id = ?",
                (user_id,)
            )

    def get_users_in_search(self) -> int:
        """Возвращает количество пользователей в поиске"""
        self.cursor.execute("SELECT COUNT(*) FROM users WHERE status = 1")
        return self.cursor.fetchone()[0]

    def close(self):
        """Закрывает соединение с базой данных"""
        self.conn.close()
