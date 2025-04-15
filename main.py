import asyncio
import os
import sqlite3
import time
from aiogram import Bot, F, Dispatcher
from aiogram.filters import Command
from aiogram.types import (
    Message, 
    CallbackQuery, 
    InlineKeyboardButton, 
    InlineKeyboardMarkup, 
    BotCommand, 
    MessageReactionUpdated,
    ReactionTypeEmoji
)
from aiogram.enums import ChatMemberStatus, ChatType, ParseMode
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

# Инициализация базы данных
class Database:
    def __init__(self, db_name):
        self.conn = sqlite3.connect(db_name)
        self._create_tables()
        
    def _create_tables(self):
        with self.conn:
            self.conn.execute('''CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                status INTEGER DEFAULT 0,
                rid INTEGER,
                interests TEXT,
                age INTEGER,
                gender TEXT,
                referrer_id INTEGER,
                invited_count INTEGER DEFAULT 0
            )''')
            
    def new_user(self, user_id, referrer_id=None):
        with self.conn:
            self.conn.execute("INSERT OR IGNORE INTO users (id) VALUES (?)", (user_id,))
            if referrer_id:
                self.conn.execute("UPDATE users SET referrer_id = ? WHERE id = ?", 
                                (referrer_id, user_id))
                self.conn.execute("UPDATE users SET invited_count = invited_count + 1 WHERE id = ?", 
                                (referrer_id,))
                
    def update_age_gender(self, user_id, age, gender):
        with self.conn:
            self.conn.execute("UPDATE users SET age = ?, gender = ? WHERE id = ?", 
                            (age, gender, user_id))
            
    def get_user(self, user_id):
        cursor = self.conn.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        return cursor.fetchone()
    
    def search(self, user_id, gender_filter=None):
        query = "SELECT * FROM users WHERE status = 1 AND id != ?"
        params = [user_id]
        
        if gender_filter:
            query += " AND gender = ?"
            params.append(gender_filter)
            
        cursor = self.conn.execute(query + " LIMIT 1", params)
        return cursor.fetchone()
    
    def start_chat(self, user1, user2):
        with self.conn:
            self.conn.execute("UPDATE users SET status = 2, rid = ? WHERE id = ?", (user2, user1))
            self.conn.execute("UPDATE users SET status = 2, rid = ? WHERE id = ?", (user1, user2))
            
    def stop_chat(self, user1, user2):
        with self.conn:
            self.conn.execute("UPDATE users SET status = 0, rid = NULL WHERE id = ?", (user1,))
            self.conn.execute("UPDATE users SET status = 0, rid = NULL WHERE id = ?", (user2,))
            
    def get_referral_info(self, user_id):
        cursor = self.conn.execute("SELECT invited_count, referrer_id FROM users WHERE id = ?", 
                                 (user_id,))
        return cursor.fetchone()

# Управление VIP статусом
class VIPManager:
    @staticmethod
    def add_vip(user_id, days=7):
        expire_time = int(time.time()) + days * 86400
        with open('vip_users.txt', 'a') as f:
            f.write(f"{user_id}:{expire_time}\n")
    
    @staticmethod
    def is_vip(user_id):
        try:
            with open('vip_users.txt', 'r') as f:
                for line in f:
                    uid, expire = line.strip().split(':')
                    if int(uid) == user_id and int(expire) > time.time():
                        return True
        except FileNotFoundError:
            open('vip_users.txt', 'w').close()
        return False

# Конфигурация бота
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не установлен!")

bot = Bot(TOKEN)
dp = Dispatcher()
db = Database("users.db")

# Клавиатуры
gender_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="👨 Мужской", callback_data="gender_male"),
     InlineKeyboardButton(text="👩 Женский", callback_data="gender_female")]
])

search_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="🔎 Найти чат", callback_data="search_chat")]
])

# Проверка подписки/статуса
async def is_subscribed(user_id: int) -> bool:
    if VIPManager.is_vip(user_id):
        return True
    try:
        member = await bot.get_chat_member("@freedom346", user_id)
        return member.status in [ChatMemberStatus.MEMBER, 
                               ChatMemberStatus.ADMINISTRATOR, 
                               ChatMemberStatus.CREATOR]
    except Exception:
        return False

# Обработчики команд
@dp.message(Command("start"))
async def start_command(message: Message):
    args = message.text.split()
    referrer_id = int(args[1][4:]) if len(args) > 1 and args[1].startswith('ref') else None
    
    user = db.get_user(message.from_user.id)
    if not user:
        db.new_user(message.from_user.id, referrer_id)
        await message.answer("👤 Пожалуйста, введите ваш возраст (14-99 лет):")
        return
    
    if not user[4] or not user[5]:
        await message.answer("👤 Пожалуйста, введите ваш возраст (14-99 лет):")
        return
    
    await message.answer(
        "👥 Добро пожаловать в Анонимный Чат Бот!\n"
        "🗣 Начните поиск собеседника:",
        reply_markup=search_keyboard
    )

@dp.message(lambda m: m.text.isdigit() and 14 <= int(m.text) <= 99)
async def process_age(message: Message):
    await message.answer("Выберите пол:", reply_markup=gender_keyboard)

@dp.callback_query(F.data.startswith("gender_"))
async def process_gender(callback: CallbackQuery):
    gender = "Мужской" if "male" in callback.data else "Женский"
    db.update_age_gender(callback.from_user.id, int(callback.message.text), gender)
    await callback.message.edit_text("✅ Данные сохранены!")
    await start_command(callback.message)

@dp.callback_query(F.data == "search_chat")
async def search_chat(callback: CallbackQuery):
    if not await is_subscribed(callback.from_user.id):
        subscribe_markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Подписаться", url="https://t.me/freedom346")],
            [InlineKeyboardButton(text="🔄 Проверить", callback_data="check_sub")]
        ])
        await callback.message.answer("⚠️ Для использования бота необходимо подписаться!", 
                                    reply_markup=subscribe_markup)
        return
    
    user = db.get_user(callback.from_user.id)
    gender_filter = "Женский" if user[5] == "Мужской" else "Мужской" if VIPManager.is_vip(callback.from_user.id) else None
    rival = db.search(callback.from_user.id, gender_filter)
    
    if rival:
        db.start_chat(callback.from_user.id, rival[0])
        vip_note = "💎 Это VIP-Пользователь\n" if VIPManager.is_vip(rival[0]) else ""
        text = (
            f"{vip_note}Собеседник найден 🐵\n"
            "/next — новый собеседник\n"
            "/stop — закончить диалог\n"
            f"<code>https://t.me/{bot.token}</code>"
        )
        await callback.message.answer(text, parse_mode=ParseMode.HTML)
        await bot.send_message(rival[0], text, parse_mode=ParseMode.HTML)
    else:
        await callback.message.answer("🔎 Ищем собеседника...")
        await asyncio.sleep(5)
        await callback.message.answer("❌ Не удалось найти подходящего собеседника")

@dp.message(Command("vip"))
async def vip_command(message: Message):
    ref_info = db.get_referral_info(message.from_user.id)
    count = ref_info[0] if ref_info else 0
    ref_link = f"https://t.me/{bot.token}?start=ref{message.from_user.id}"
    
    if count >= 5 and not VIPManager.is_vip(message.from_user.id):
        VIPManager.add_vip(message.from_user.id)
        
    status = "💎 VIP активен" if VIPManager.is_vip(message.from_user.id) else "❌ VIP не активен"
    
    text = (
        f"{status}\n"
        f"👥 Приглашено: {count}/5\n"
        f"🔗 Реферальная ссылка:\n{ref_link}"
    )
    await message.answer(text)

@dp.message(Command("stop"))
async def stop_command(message: Message):
    user = db.get_user(message.from_user.id)
    if user and user[1] == 2:
        db.stop_chat(message.from_user.id, user[2])
        await message.answer("Диалог завершен")

@dp.message(Command("next"))
async def next_command(message: Message):
    await stop_command(message)
    await search_chat(message)

# Запуск бота
async def main():
    await bot.set_my_commands([
        BotCommand(command="/start", description="Начать"),
        BotCommand(command="/stop", description="Закончить диалог"),
        BotCommand(command="/next", description="Новый собеседник"),
        BotCommand(command="/vip", description="VIP статус")
    ])
    
    app = web.Application()
    SimpleRequestHandler(dp, bot).register(app, "/webhook")
    setup_application(app, dp, bot=bot)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", int(os.getenv("PORT", 10000)))
    await site.start()
    
    print("Бот запущен!")
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
