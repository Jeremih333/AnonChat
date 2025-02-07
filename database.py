class database:
    def __init__(self, db_name: str):
        # Инициализация таблицы пользователей с новыми полями
        self.users_db = db(
            db_name, 
            "users",
            """
                id INTEGER PRIMARY KEY,
                status INTEGER DEFAULT 0,
                rid INTEGER DEFAULT 0,
                gender TEXT,
                age INTEGER,
                vip INTEGER DEFAULT 0,
                referral_count INTEGER DEFAULT 0,
                referrer_id INTEGER,
                vip_expiry DATETIME
            """
        )
        # Создание индексов для быстрого поиска
        self.users_db.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_gender_age ON users(gender, age)"
        )

    def get_user_cursor(self, user_id: int) -> dict:
        result = self.users_db.select("*", {"id": user_id}, False)
        if result:
            return {
                "status": result[1],
                "rid": result[2],
                "gender": result[3],
                "age": result[4],
                "vip": result[5],
                "referral_count": result[6],
                "referrer_id": result[7],
                "vip_expiry": result[8]
            }
        return None

    def update_gender_age(self, user_id: int, gender: str, age: int):
        self.users_db.update(
            {"gender": gender, "age": age},
            {"id": user_id}
        )

    def increment_referral_count(self, user_id: int):
        self.users_db.execute(
            "UPDATE users SET referral_count = referral_count + 1 WHERE id = ?",
            (user_id,)
        )

    def activate_vip(self, user_id: int, expiry_date: str):
        self.users_db.update(
            {"vip": 1, "vip_expiry": expiry_date},
            {"id": user_id}
        )

    def search_vip(self, user_id: int, gender: str = None, min_age: int = None, max_age: int = None):
        # Базовая часть запроса
        query = "SELECT * FROM users WHERE status = 1 AND id != ?"
        params = [user_id]
        
        # Добавление фильтров
        if gender:
            query += " AND gender = ?"
            params.append(gender)
        if min_age is not None and max_age is not None:
            query += " AND age BETWEEN ? AND ?"
            params.extend([min_age, max_age])
        
        # Выполнение запроса
        return self.users_db.execute(query, params).fetchall()
