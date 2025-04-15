import sqlite3
from typing import Optional, List, Dict

class database:
    def __init__(self, db_name: str):
        self.conn = sqlite3.connect(db_name)
        self.cursor = self.conn.cursor()
        self._create_tables()
        self._migrate_database()

    def _create_tables(self):
        """Создание таблиц с актуальной структурой"""
        self.cursor.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                status INTEGER DEFAULT 0,
                rid INTEGER DEFAULT 0,
                interests TEXT DEFAULT '',
                age INTEGER,
                gender TEXT,
                referrer_id INTEGER,
                invited_count INTEGER DEFAULT 0
            );
            
            CREATE TABLE IF NOT EXISTS message_links (
                user_id INTEGER,
                message_id INTEGER,
                rival_message_id INTEGER,
                PRIMARY KEY(user_id, message_id)
            );
        """)
        self.conn.commit()

    def _migrate_database(self):
        """Миграции для существующих баз"""
        try:
            self.cursor.execute("PRAGMA table_info(users)")
            columns = [col[1] for col in self.cursor.fetchall()]
            
            # Список необходимых миграций
            migrations = {
                'age': 'INTEGER',
                'gender': 'TEXT',
                'referrer_id': 'INTEGER',
                'invited_count': 'INTEGER DEFAULT 0'
            }
            
            # Применяем недостающие миграции
            for column, data_type in migrations.items():
                if column not in columns:
                    self.cursor.execute(f"""
                        ALTER TABLE users 
                        ADD COLUMN {column} {data_type}
                    """)
            self.conn.commit()
        except sqlite3.Error as e:
            print(f"Ошибка миграции: {e}")

    def new_user(self, user_id: int, referrer_id: Optional[int] = None):
        """Добавление нового пользователя"""
        try:
            self.cursor.execute(
                "INSERT INTO users (id) VALUES (?)",
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
            
            self.conn.commit()
        except sqlite3.IntegrityError:
            pass

    def get_referral_info(self, user_id: int) -> Dict:
        """Получение реферальной информации"""
        self.cursor.execute(
            "SELECT invited_count, referrer_id FROM users WHERE id = ?",
            (user_id,)
        )
        result = self.cursor.fetchone()
        return {
            "invited_count": result[0] if result else 0,
            "referrer_id": result[1] if result else None
        }

    def search(self, user_id: int, gender_filter: Optional[str] = None) -> Optional[Dict]:
        """Поиск собеседника с фильтрацией"""
        current_user = self.get_user_cursor(user_id)
        if not current_user:
            return None

        # Обновляем статус поиска
        self.cursor.execute(
            "UPDATE users SET status = 1 WHERE id = ?",
            (user_id,)
        )
        self.conn.commit()

        # Формируем запрос
        query = """
            SELECT id, interests, gender 
            FROM users 
            WHERE status = 1 
            AND id != ?
            AND status != 2
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

    def get_user_cursor(self, user_id: int) -> Optional[Dict]:
        """Получение полной информации о пользователе"""
        self.cursor.execute(
            "SELECT * FROM users WHERE id = ?",
            (user_id,)
        )
        columns = [col[0] for col in self.cursor.description]
        row = self.cursor.fetchone()
        return dict(zip(columns, row)) if row else None

    def start_chat(self, user1: int, user2: int):
        """Начало чата между пользователями"""
        self.cursor.executemany(
            "UPDATE users SET status = 2, rid = ? WHERE id = ?",
            [(user2, user1), (user1, user2)]
        )
        self.conn.commit()

    def stop_chat(self, user1: int, user2: int):
        """Завершение чата"""
        self.cursor.executemany(
            "UPDATE users SET status = 0, rid = 0 WHERE id = ?",
            [(user1,), (user2,)]
        )
        self.conn.commit()

    def stop_search(self, user_id: int):
        """Остановка поиска"""
        self.cursor.execute(
            "UPDATE users SET status = 0 WHERE id = ?",
            (user_id,)
        )
        self.conn.commit()

    def save_message_link(self, user_id: int, message_id: int, rival_id: int):
        """Сохранение связи сообщений"""
        self.cursor.execute(
            "INSERT INTO message_links VALUES (?, ?, ?)",
            (user_id, message_id, rival_id)
        )
        self.conn.commit()

    def get_rival_message_id(self, user_id: int, original_id: int) -> Optional[int]:
        """Получение ID связанного сообщения"""
        self.cursor.execute(
            "SELECT rival_message_id FROM message_links WHERE user_id = ? AND message_id = ?",
            (user_id, original_id)
        )
        result = self.cursor.fetchone()
        return result[0] if result else None

    def add_interest(self, user_id: int, interest: str):
        """Добавление интереса"""
        interests = self.get_user_interests(user_id)
        if interest not in interests:
            interests.append(interest)
            self._update_interests(user_id, interests)

    def remove_interest(self, user_id: int, interest: str):
        """Удаление интереса"""
        interests = self.get_user_interests(user_id)
        if interest in interests:
            interests.remove(interest)
            self._update_interests(user_id, interests)

    def clear_interests(self, user_id: int):
        """Очистка интересов"""
        self._update_interests(user_id, [])

    def get_user_interests(self, user_id: int) -> List[str]:
        """Получение списка интересов"""
        self.cursor.execute(
            "SELECT interests FROM users WHERE id = ?",
            (user_id,)
        )
        result = self.cursor.fetchone()
        return result[0].split(',') if result and result[0] else []

    def _update_interests(self, user_id: int, interests: List[str]):
        """Обновление интересов в БД"""
        self.cursor.execute(
            "UPDATE users SET interests = ? WHERE id = ?",
            (','.join(interests), user_id)
        )
        self.conn.commit()

    def get_users_in_search(self) -> List[int]:
        """Получение ID пользователей в поиске"""
        self.cursor.execute("SELECT id FROM users WHERE status = 1")
        return [row[0] for row in self.cursor.fetchall()]

    def close(self):
        """Закрытие соединения с БД"""
        self.conn.close()
