import sqlite3

class database:
    def __init__(self, db_name: str):
        self.conn = sqlite3.connect(db_name)
        self.cursor = self.conn.cursor()
        
        # Создаём таблицы при инициализации
        self._create_tables()
    
    def _create_tables(self):
        """Создаёт необходимые таблицы в базе данных"""
        # Таблица пользователей
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                status INTEGER DEFAULT 0,
                rid INTEGER DEFAULT 0,
                interests TEXT DEFAULT ''
            )
        """)
        
        # Таблица связей сообщений
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS message_links (
                user_id INTEGER,
                message_id INTEGER,
                rival_message_id INTEGER,
                PRIMARY KEY(user_id, message_id)
            )
        """)
        self.conn.commit()

    # Основные методы работы с пользователями
    def get_user_cursor(self, user_id: int) -> dict:
        """Получает информацию о пользователе"""
        self.cursor.execute(
            "SELECT id, status, rid, interests FROM users WHERE id = ?",
            (user_id,)
        )
        result = self.cursor.fetchone()
        if not result:
            return None
        return {
            "id": result[0],
            "status": result[1],
            "rid": result[2],
            "interests": result[3] if result[3] else ''
        }

    def new_user(self, user_id: int):
        """Добавляет нового пользователя"""
        self.cursor.execute(
            "INSERT INTO users (id) VALUES (?)",
            (user_id,)
        )
        self.conn.commit()

    def search(self, user_id: int):
        """Поиск подходящего собеседника"""
        current_user = self.get_user_cursor(user_id)
        if not current_user:
            return None

        # Обновляем статус пользователя на "в поиске"
        self.cursor.execute(
            "UPDATE users SET status = 1, rid = 0 WHERE id = ?",
            (user_id,)
        )
        self.conn.commit()

        # Получаем интересы текущего пользователя
        user_interests = set(current_user['interests'].split(',')) if current_user['interests'] else set()

        # Ищем кандидатов
        self.cursor.execute(
            "SELECT id, interests FROM users WHERE status = 1 AND id != ?",
            (user_id,)
        )
        candidates = []
        for candidate in self.cursor.fetchall():
            c_id, c_interests = candidate
            candidate_interests = set(c_interests.split(',')) if c_interests else set()
            
            # Проверяем совпадение интересов
            if not user_interests or user_interests & candidate_interests:
                candidates.append({
                    "id": c_id,
                    "interests": candidate_interests
                })

        # Сортируем по количеству совпадений
        candidates.sort(
            key=lambda x: len(user_interests & x['interests']),
            reverse=True
        )

        return candidates[0] if candidates else None

    def start_chat(self, user_id: int, rival_id: int):
        """Начинает чат между двумя пользователями"""
        self.cursor.executemany(
            "UPDATE users SET status = 2, rid = ? WHERE id = ?",
            [(rival_id, user_id), (user_id, rival_id)]
        )
        self.conn.commit()

    def stop_chat(self, user_id: int, rival_id: int):
        """Завершает чат между пользователями"""
        self.cursor.executemany(
            "UPDATE users SET status = 0, rid = 0 WHERE id = ?",
            [(user_id,), (rival_id,)]
        )
        self.conn.commit()

    def stop_search(self, user_id: int):
        """Останавливает поиск собеседника"""
        self.cursor.execute(
            "UPDATE users SET status = 0, rid = 0 WHERE id = ?",
            (user_id,)
        )
        self.conn.commit()

    # Работа с сообщениями
    def save_message_link(self, user_id: int, message_id: int, rival_message_id: int):
        """Сохраняет связь между сообщениями"""
        self.cursor.execute(
            "INSERT INTO message_links VALUES (?, ?, ?)",
            (user_id, message_id, rival_message_id)
        )
        self.conn.commit()

    def get_rival_message_id(self, user_id: int, message_id: int) -> int:
        """Получает ID связанного сообщения"""
        self.cursor.execute(
            "SELECT rival_message_id FROM message_links WHERE user_id = ? AND message_id = ?",
            (user_id, message_id)
        )
        result = self.cursor.fetchone()
        return result[0] if result else None

    # Работа с интересами
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

    def clear_interests(self, user_id: int):
        """Очищает все интересы пользователя"""
        self._update_interests(user_id, [])

    def get_user_interests(self, user_id: int) -> list:
        """Возвращает список интересов пользователя"""
        self.cursor.execute(
            "SELECT interests FROM users WHERE id = ?",
            (user_id,)
        )
        result = self.cursor.fetchone()
        return result[0].split(',') if result and result[0] else []

    def _update_interests(self, user_id: int, interests: list):
        """Обновляет интересы пользователя в базе"""
        self.cursor.execute(
            "UPDATE users SET interests = ? WHERE id = ?",
            (','.join(interests), user_id)
        )
        self.conn.commit()

    # Дополнительные методы
    def get_users_in_search(self) -> int:
        """Возвращает количество пользователей в поиске"""
        self.cursor.execute("SELECT COUNT(*) FROM users WHERE status = 1")
        return self.cursor.fetchone()[0]

    def close(self):
        """Закрывает соединение с базой данных"""
        self.conn.close()
