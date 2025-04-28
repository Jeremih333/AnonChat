import sqlite3
from datetime import datetime, timedelta

class Database:
    def __init__(self, db_name: str):
        self.conn = sqlite3.connect(db_name)
        self.conn.row_factory = sqlite3.Row
        self.cursor = self.conn.cursor()
        self._create_tables()
        self._migrate_database()

    def _create_tables(self):
        """Создание таблиц с актуальной структурой"""
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                status INTEGER DEFAULT 0,
                rid INTEGER DEFAULT 0,
                interests TEXT DEFAULT '',
                blocked BOOLEAN DEFAULT 0,
                blocked_until TEXT DEFAULT NULL,
                search_started TEXT DEFAULT NULL,
                gender TEXT DEFAULT NULL,
                age INTEGER DEFAULT NULL,
                vip_until TEXT DEFAULT NULL,
                referral_code TEXT UNIQUE,
                invited_by INTEGER DEFAULT NULL,
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
        
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sender_id INTEGER,
                receiver_id INTEGER,
                content TEXT,
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_ratings (
                user_id INTEGER PRIMARY KEY,
                positive INTEGER DEFAULT 0,
                negative INTEGER DEFAULT 0
            )
        """)
        
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS last_rivals (
                user_id INTEGER PRIMARY KEY,
                rival_id INTEGER
            )
        """)
        self.conn.commit()

    def _migrate_database(self):
        """Миграции для существующих баз данных"""
        try:
            self.cursor.execute("PRAGMA table_info(users)")
            columns = [column[1] for column in self.cursor.fetchall()]
            
            # Добавление новых столбцов при необходимости
            new_columns = {
                'gender': "ALTER TABLE users ADD COLUMN gender TEXT DEFAULT NULL",
                'age': "ALTER TABLE users ADD COLUMN age INTEGER DEFAULT NULL",
                'vip_until': "ALTER TABLE users ADD COLUMN vip_until TEXT DEFAULT NULL",
                'referral_code': "ALTER TABLE users ADD COLUMN referral_code TEXT UNIQUE",
                'invited_by': "ALTER TABLE users ADD COLUMN invited_by INTEGER DEFAULT NULL",
                'invited_count': "ALTER TABLE users ADD COLUMN invited_count INTEGER DEFAULT 0"
            }
            
            for col, query in new_columns.items():
                if col not in columns:
                    self.cursor.execute(query)
            
            self.conn.commit()
        except sqlite3.Error as e:
            print(f"Migration error: {e}")

    def get_user_cursor(self, user_id: int) -> dict:
        """Получение информации о пользователе"""
        self.cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        result = self.cursor.fetchone()
        return dict(result) if result else None

    def new_user(self, user_id: int):
        """Добавляет нового пользователя с генерацией реферального кода"""
        self.cursor.execute(
            "INSERT OR IGNORE INTO users (id) VALUES (?)",
            (user_id,)
        )
        # Генерация реферального кода
        code = f"ref{user_id}"
        self.cursor.execute(
            "UPDATE users SET referral_code = ? WHERE id = ?",
            (code, user_id)
        )
        self.conn.commit()

    def update_user_info(self, user_id: int, gender: str, age: int):
        """Обновление информации о пользователе"""
        self.cursor.execute(
            "UPDATE users SET gender = ?, age = ? WHERE id = ?",
            (gender, age, user_id)
        )
        self.conn.commit()

    def get_referral_code(self, user_id: int) -> str:
        """Получение реферального кода пользователя"""
        self.cursor.execute("SELECT referral_code FROM users WHERE id = ?", (user_id,))
        row = self.cursor.fetchone()
        return row['referral_code'] if row else None

    def handle_referral(self, user_id: int, referrer_id: int):
        """Обработка реферального приглашения"""
        # Обновляем счетчик пригласившего
        self.cursor.execute(
            "UPDATE users SET invited_count = invited_count + 1 WHERE id = ?",
            (referrer_id,)
        )
        # Добавляем VIP дни пригласившему
        self.add_vip_days(referrer_id, 1)
        # Сохраняем информацию о пригласившем
        self.cursor.execute(
            "UPDATE users SET invited_by = ? WHERE id = ?",
            (referrer_id, user_id)
        )
        self.conn.commit()

    def add_vip_days(self, user_id: int, days: int):
        """Добавление VIP статуса на указанное количество дней"""
        user = self.get_user_cursor(user_id)
        if not user:
            return
        
        current_vip = datetime.fromisoformat(user['vip_until']) if user['vip_until'] else datetime.now()
        new_vip = max(current_vip, datetime.now()) + timedelta(days=days)
        
        self.cursor.execute(
            "UPDATE users SET vip_until = ? WHERE id = ?",
            (new_vip.isoformat(), user_id)
        )
        self.conn.commit()

    def get_vip_status(self, user_id: int) -> bool:
        """Проверка VIP статуса"""
        user = self.get_user_cursor(user_id)
        if not user or not user['vip_until']:
            return False
        return datetime.fromisoformat(user['vip_until']) > datetime.now()

    def search(self, user_id: int):
        """Улучшенный поиск с учетом VIP статуса и пола"""
        current_user = self.get_user_cursor(user_id)
        if not current_user:
            return None

        now_str = datetime.now().isoformat()
        self.cursor.execute(
            "UPDATE users SET status = 1, rid = 0, search_started = ? WHERE id = ?",
            (now_str, user_id)
        )
        self.conn.commit()

        # Формируем базовый запрос
        query = """
            SELECT id, interests, gender FROM users 
            WHERE status = 1 
            AND id != ?
            AND blocked = 0
            AND (blocked_until IS NULL OR blocked_until < ?)
        """
        params = [user_id, now_str]

        # Если пользователь VIP и указал пол, добавляем фильтр по полу
        if self.get_vip_status(user_id) and current_user['gender']:
            gender_preference = 'женский' if current_user['gender'] == 'мужской' else 'мужской'
            query += " AND gender = ?"
            params.append(gender_preference)

        self.cursor.execute(query, params)
        candidates = []
        
        for candidate in self.cursor.fetchall():
            c_id = candidate['id']
            c_interests = set(candidate['interests'].split(',')) if candidate['interests'] else set()
            user_interests = set(current_user['interests'].split(',')) if current_user['interests'] else set()

            # Получаем рейтинг кандидата
            c_rating = self.get_user_rating(c_id)
            
            candidates.append({
                "id": c_id,
                "interests": c_interests,
                "positive": c_rating['positive'],
                "negative": c_rating['negative'],
                "common_interests": len(user_interests & c_interests)
            })

        # Сортировка по приоритету:
        # 1. Количество общих интересов
        # 2. Позитивный рейтинг
        # 3. Отсутствие негативного рейтинга
        candidates.sort(
            key=lambda x: (-x['common_interests'], -x['positive'], x['negative']), 
            reverse=True
        )

        return candidates[0] if candidates else None

    def block_user(self, user_id: int, block_until: datetime = None, permanent=False):
        """Блокировка пользователя с возможностью указания времени"""
        if permanent:
            self.cursor.execute(
                "UPDATE users SET blocked = 1, blocked_until = NULL WHERE id = ?",
                (user_id,)
            )
        else:
            until_str = block_until.isoformat() if block_until else None
            self.cursor.execute(
                "UPDATE users SET blocked = 1, blocked_until = ? WHERE id = ?",
                (until_str, user_id)
            )
        self.conn.commit()

    def unblock_user(self, user_id: int):
        """Полная разблокировка пользователя"""
        self.cursor.execute(
            "UPDATE users SET blocked = 0, blocked_until = NULL WHERE id = ?",
            (user_id,)
        )
        self.conn.commit()

    # Остальные методы остаются с небольшими корректировками для работы с новой структурой

    def start_chat(self, user_id: int, rival_id: int):
        self.cursor.executemany(
            "UPDATE users SET status = 2, rid = ?, search_started = NULL WHERE id = ?",
            [(rival_id, user_id), (user_id, rival_id)]
        )
        self.cursor.execute("INSERT OR REPLACE INTO last_rivals (user_id, rival_id) VALUES (?, ?)", (user_id, rival_id))
        self.cursor.execute("INSERT OR REPLACE INTO last_rivals (user_id, rival_id) VALUES (?, ?)", (rival_id, user_id))
        self.conn.commit()

    def stop_chat(self, user_id: int, rival_id: int):
        self.cursor.executemany(
            "UPDATE users SET status = 0, rid = 0, search_started = NULL WHERE id = ?",
            [(user_id,), (rival_id,)]
        )
        self.conn.commit()

    def get_user_interests(self, user_id: int) -> list:
        self.cursor.execute("SELECT interests FROM users WHERE id = ?", (user_id,))
        result = self.cursor.fetchone()
        return result[0].split(',') if result and result[0] else []

    def _update_interests(self, user_id: int, interests: list):
        self.cursor.execute(
            "UPDATE users SET interests = ? WHERE id = ?",
            (','.join(interests), user_id)
        )
        self.conn.commit()

    def get_expired_blocks(self, now: datetime):
        self.cursor.execute("SELECT * FROM users WHERE blocked = 1 AND blocked_until IS NOT NULL")
        return [dict(row) for row in self.cursor.fetchall() if datetime.fromisoformat(row['blocked_until']) < now]

    def block_user(self, user_id: int, block_until: datetime = None, permanent=False):
        if permanent:
            self.cursor.execute(
                "UPDATE users SET blocked = 1, blocked_until = NULL WHERE id = ?",
                (user_id,)
            )
        else:
            until_str = block_until.isoformat() if block_until else None
            self.cursor.execute(
                "UPDATE users SET blocked = 1, blocked_until = ? WHERE id = ?",
                (until_str, user_id)
            )
        self.conn.commit()

    def unblock_user(self, user_id: int):
        self.cursor.execute(
            "UPDATE users SET blocked = 0, blocked_until = NULL WHERE id = ?",
            (user_id,)
        )
        self.conn.commit()

    def save_message(self, sender_id: int, receiver_id: int, content: str):
        self.cursor.execute(
            "INSERT INTO messages (sender_id, receiver_id, content) VALUES (?, ?, ?)",
            (sender_id, receiver_id, content)
        )
        self.conn.commit()

    def get_chat_log(self, user1_id: int, user2_id: int, limit=10):
        self.cursor.execute('''
            SELECT * FROM messages 
            WHERE (sender_id = ? AND receiver_id = ?) OR (sender_id = ? AND receiver_id = ?)
            ORDER BY timestamp DESC LIMIT ?
        ''', (user1_id, user2_id, user2_id, user1_id, limit))
        return [dict(row) for row in self.cursor.fetchall()]

    def add_rating(self, user_id: int, rating: int):
        """Добавляет рейтинг пользователю: rating = 1 (положительный) или -1 (негативный)"""
        self.cursor.execute("SELECT positive, negative FROM user_ratings WHERE user_id = ?", (user_id,))
        row = self.cursor.fetchone()
        if row:
            positive, negative = row['positive'], row['negative']
            if rating > 0:
                positive += 1
            else:
                negative += 1
            self.cursor.execute(
                "UPDATE user_ratings SET positive = ?, negative = ? WHERE user_id = ?",
                (positive, negative, user_id)
            )
        else:
            positive = 1 if rating > 0 else 0
            negative = 1 if rating < 0 else 0
            self.cursor.execute(
                "INSERT INTO user_ratings (user_id, positive, negative) VALUES (?, ?, ?)",
                (user_id, positive, negative)
            )
        self.conn.commit()

    def get_user_rating(self, user_id: int):
        self.cursor.execute("SELECT positive, negative FROM user_ratings WHERE user_id = ?", (user_id,))
        row = self.cursor.fetchone()
        if row:
            return {"positive": row["positive"], "negative": row["negative"]}
        else:
            return {"positive": 0, "negative": 0}

    def get_last_rival(self, user_id: int):
        """Возвращает id последнего собеседника пользователя"""
        self.cursor.execute("SELECT rival_id FROM last_rivals WHERE user_id = ?", (user_id,))
        row = self.cursor.fetchone()
        return row["rival_id"] if row else None

    def close(self):
        """Закрывает соединение с базой данных"""
        self.conn.close()
