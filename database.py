import sqlite3
from typing import Optional, List, Dict

class Database:
    def __init__(self, db_name: str = 'bot_database.db'):
        self.conn = sqlite3.connect(db_name, check_same_thread=False)
        self.cursor = self.conn.cursor()
        self._initialize_database()

    def _initialize_database(self):
        """Инициализация структуры базы данных"""
        with self.conn:
            # Основная таблица пользователей
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY,
                    status INTEGER DEFAULT 0 CHECK(status IN (0, 1, 2)),
                    rid INTEGER DEFAULT 0,
                    interests TEXT DEFAULT '',
                    age INTEGER CHECK(age BETWEEN 12 AND 100),
                    gender TEXT CHECK(gender IN ('M', 'F', 'Other')),
                    referrer_id INTEGER,
                    invited_count INTEGER DEFAULT 0,
                    vip_level INTEGER DEFAULT 0,
                    FOREIGN KEY(referrer_id) REFERENCES users(id)
                )
            """)
            
            # Таблица связей сообщений
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS message_links (
                    user_id INTEGER NOT NULL,
                    message_id INTEGER NOT NULL,
                    rival_id INTEGER NOT NULL,
                    PRIMARY KEY(user_id, message_id),
                    FOREIGN KEY(user_id) REFERENCES users(id)
                )
            """)
            
        # Применение миграций
        self._apply_migrations()

    def _apply_migrations(self):
        """Система миграций для обновления структуры"""
        required_columns = {
            'status': 'INTEGER DEFAULT 0',
            'rid': 'INTEGER DEFAULT 0',
            'interests': 'TEXT DEFAULT ""',
            'age': 'INTEGER',
            'gender': 'TEXT',
            'referrer_id': 'INTEGER',
            'invited_count': 'INTEGER DEFAULT 0',
            'vip_level': 'INTEGER DEFAULT 0'
        }

        with self.conn:
            try:
                # Получаем информацию о существующих столбцах
                self.cursor.execute("PRAGMA table_info(users)")
                existing_columns = {row[1]: row for row in self.cursor.fetchall()}

                # Добавляем отсутствующие столбцы
                for column, data_type in required_columns.items():
                    if column not in existing_columns:
                        self.cursor.execute(
                            f"ALTER TABLE users ADD COLUMN {column} {data_type}"
                        )
                self.conn.commit()
            except sqlite3.Error as e:
                print(f"Ошибка при миграции: {str(e)}")
                self.conn.rollback()

    def create_user(self, user_id: int, referrer_id: Optional[int] = None):
        """Создание нового пользователя"""
        with self.conn:
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
            except sqlite3.IntegrityError:
                pass

    def get_user(self, user_id: int) -> Optional[Dict]:
        """Получение информации о пользователе"""
        self.cursor.execute(
            "SELECT * FROM users WHERE id = ?",
            (user_id,)
        )
        columns = [col[0] for col in self.cursor.description]
        row = self.cursor.fetchone()
        return dict(zip(columns, row)) if row else None

    def search(self, user_id: int, gender_filter: Optional[str] = None) -> Optional[Dict]:
        """Поиск подходящего собеседника"""
        current_user = self.get_user(user_id)
        if not current_user:
            return None

        # Обновляем статус поиска
        with self.conn:
            self.cursor.execute(
                "UPDATE users SET status = 1 WHERE id = ?",
                (user_id,)
            )

        # Формируем запрос поиска
        query = """
            SELECT id, interests, gender, age 
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
        
        if candidate:
            return {
                "id": candidate[0],
                "interests": candidate[1].split(',') if candidate[1] else [],
                "gender": candidate[2],
                "age": candidate[3]
            }
        return None

    def start_chat(self, user1: int, user2: int):
        """Начало чата между двумя пользователями"""
        with self.conn:
            self.cursor.executemany(
                "UPDATE users SET status = 2, rid = ? WHERE id = ?",
                [(user2, user1), (user1, user2)]
            )

    def stop_chat(self, user1: int, user2: int):
        """Завершение текущего чата"""
        with self.conn:
            self.cursor.executemany(
                "UPDATE users SET status = 0, rid = 0 WHERE id = ?",
                [(user1,), (user2,)]
            )

    def update_interests(self, user_id: int, interests: List[str]):
        """Обновление списка интересов пользователя"""
        with self.conn:
            self.cursor.execute(
                "UPDATE users SET interests = ? WHERE id = ?",
                (','.join(interests), user_id)
            )

    def get_referral_info(self, user_id: int) -> Dict:
        """Получение реферальной статистики"""
        self.cursor.execute(
            "SELECT invited_count, referrer_id FROM users WHERE id = ?",
            (user_id,)
        )
        result = self.cursor.fetchone()
        return {
            "invited_count": result[0] if result else 0,
            "referrer_id": result[1] if result else None
        }

    def save_message_link(self, user_id: int, message_id: int, rival_id: int):
        """Сохранение связи между сообщениями"""
        with self.conn:
            self.cursor.execute(
                "INSERT INTO message_links VALUES (?, ?, ?)",
                (user_id, message_id, rival_id)
            )

    def get_linked_message(self, user_id: int, message_id: int) -> Optional[int]:
        """Получение связанного ID сообщения"""
        self.cursor.execute(
            "SELECT rival_id FROM message_links WHERE user_id = ? AND message_id = ?",
            (user_id, message_id)
        )
        result = self.cursor.fetchone()
        return result[0] if result else None

    def add_vip_status(self, user_id: int, days: int):
        """Добавление VIP-статуса"""
        with self.conn:
            self.cursor.execute(
                "UPDATE users SET vip_level = ? WHERE id = ?",
                (days, user_id)
            )

    def close(self):
        """Закрытие соединения с базой данных"""
        self.conn.close()
