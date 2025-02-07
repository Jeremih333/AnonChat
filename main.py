import asyncio
import os
import uuid
from datetime import datetime, timedelta
from aiogram import Bot, F, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import (
    Message, 
    CallbackQuery, 
    InlineKeyboardButton, 
    InlineKeyboardMarkup,
    BotCommand
)
from aiogram.enums import ChatMemberStatus, ChatType
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiohttp import web

# Ваши модули
from database import database
from keyboard import online

class Form(StatesGroup):
    gender = State()
    age = State()
    vip_filter = State()

if not (token := os.getenv("TELEGRAM_BOT_TOKEN")):
    raise ValueError("TELEGRAM_BOT_TOKEN не установлен!")

WEBHOOK_URL = os.getenv("WEBHOOK_URL", "https://your-service.onrender.com")
PORT = int(os.getenv("PORT", 10000))

bot = Bot(token)
dp = Dispatcher()
db = database("users.db")

# Инициализация базы данных
db.execute('''CREATE TABLE IF NOT EXISTS users
             (id INTEGER PRIMARY KEY, 
             status INTEGER, 
             rid INTEGER, 
             gender TEXT, 
             age INTEGER,
             vip INTEGER DEFAULT 0,
             referral_count INTEGER DEFAULT 0,
             referrer_id INTEGER,
             vip_expiry DATETIME)''')

async def is_subscribed(user_id: int) -> bool:
    try:
        member = await bot.get_chat_member("@freedom346", user_id)
        return member.status in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR]
    except Exception:
        return False

def check_vip_status(user_id: int) -> bool:
    user = db.get_user_cursor(user_id)
    if user and user['vip'] and user['vip_expiry']:
        expiry_date = datetime.strptime(user['vip_expiry'], '%Y-%m-%d %H:%M:%S')
        return datetime.now() < expiry_date
    return False

def gender_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👨 Мужской", callback_data="gender_male"),
         InlineKeyboardButton(text="👩 Женский", callback_data="gender_female")]
    ])

async def request_age(message: Message):
    await message.answer("📅 Пожалуйста, введите ваш возраст (от 13 до 100):")
    await Form.age.set()

@dp.message(Command("start"))
async def start_command(message: Message, state: FSMContext):
    args = message.text.split()
    user = db.get_user_cursor(message.from_user.id)
    
    # Обработка реферальной ссылки
    if len(args) > 1 and args[1].startswith('ref'):
        referrer_id = args[1][3:]
        if referrer_id.isdigit() and int(referrer_id) != message.from_user.id:
            db.execute("UPDATE users SET referral_count = referral_count + 1 WHERE id = ?", 
                      (int(referrer_id),))
            # Проверка и активация VIP
            referrer = db.get_user_cursor(int(referrer_id))
            if referrer and referrer['referral_count'] + 1 >= 5:
                expiry = datetime.now() + timedelta(days=30)
                db.execute("UPDATE users SET vip = 1, vip_expiry = ? WHERE id = ?",
                          (expiry.strftime('%Y-%m-%d %H:%M:%S'), referrer_id))

    if not user:
        db.new_user(message.from_user.id)
        await message.answer("👤 Пожалуйста, выберите ваш пол:", reply_markup=gender_keyboard())
        await Form.gender.set()
    else:
        if not user.get('gender') or not user.get('age'):
            await message.answer("❌ Для использования бота необходимо завершить регистрацию!")
            await start_registration(message)
        else:
            await main_menu(message)

async def start_registration(message: Message):
    await message.answer("👤 Пожалуйста, выберите ваш пол:", reply_markup=gender_keyboard())
    await Form.gender.set()

@dp.callback_query(F.data.startswith("gender_"))
async def process_gender(callback: CallbackQuery, state: FSMContext):
    gender = callback.data.split('_')[1]
    db.execute("UPDATE users SET gender = ? WHERE id = ?", 
              (gender, callback.from_user.id))
    await callback.message.edit_text(f"✅ Ваш пол: {'👨 Мужской' if gender == 'male' else '👩 Женский'}")
    await request_age(callback.message)
    await state.clear()

@dp.message(Form.age)
async def process_age(message: Message, state: FSMContext):
    if not message.text.isdigit() or not (13 <= int(message.text) <= 100):
        await message.answer("❌ Некорректный возраст! Введите число от 13 до 100:")
        return
    
    age = int(message.text)
    db.execute("UPDATE users SET age = ? WHERE id = ?", (age, message.from_user.id))
    await state.clear()
    await main_menu(message)
    await message.answer("✅ Регистрация завершена!")

async def main_menu(message: Message):
    user = db.get_user_cursor(message.from_user.id)
    text = "👋 Добро пожаловать!\n"
    if check_vip_status(message.from_user.id):
        text += "🌟 Ваш VIP статус активен!\n"
    await message.answer(text, reply_markup=online.builder("🔎 Найти чат"))

@dp.message(F.text == "🔎 Найти чат")
async def search_chat(message: Message):
    user = db.get_user_cursor(message.from_user.id)
    
    if not user.get('gender') or not user.get('age'):
        await message.answer("❌ Завершите регистрацию!")
        await start_registration(message)
        return
    
    if not await is_subscribed(message.from_user.id):
        # Кнопка подписки
        return
    
    # VIP фильтрация
    if check_vip_status(message.from_user.id):
        await message.answer("⚙️ Выберите параметры поиска:",
                           reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                               [InlineKeyboardButton(text="Пол", callback_data="filter_gender"),
                                InlineKeyboardButton(text="Возраст", callback_data="filter_age")]
                           ]))
        await Form.vip_filter.set()
    else:
        await start_search(message)

async def start_search(message: Message):
    # Обычный поиск
    rival = db.search(message.from_user.id)
    # ... (остальная логика поиска)

@dp.callback_query(F.data == "filter_gender")
async def filter_gender(callback: CallbackQuery):
    await callback.message.edit_text("Выберите пол для поиска:",
                                    reply_markup=gender_keyboard())

@dp.callback_query(F.data == "filter_age")
async def filter_age(callback: CallbackQuery):
    await callback.message.answer("Введите возрастной диапазон (например: 18-30):")

@dp.message(Form.vip_filter)
async def process_vip_filter(message: Message, state: FSMContext):
    # Обработка фильтров VIP
    pass

@dp.message(Command("referral"))
async def referral_command(message: Message):
    ref_link = f"https://t.me/{(await bot.get_me()).username}?start=ref{message.from_user.id}"
    await message.answer(f"🔗 Ваша реферальная ссылка:\n{ref_link}\n\n"
                        "Пригласите 5 друзей для получения VIP статуса на 1 месяц!")

# Остальные обработчики (stop, next, link и т.д.) остаются аналогичными, 
# с добавлением проверок на регистрацию и VIP статус

async def main():
    # Инициализация команд бота
    await bot.set_my_commands([
        BotCommand(command="/start", description="Начать"),
        BotCommand(command="/stop", description="Стоп"),
        BotCommand(command="/referral", description="Реферальная ссылка"),
        BotCommand(command="/vip", description="VIP статус")
    ])
    
    # Настройка веб-сервера
    app = web.Application()
    webhook_requests_handler = SimpleRequestHandler(dp, bot)
    webhook_requests_handler.register(app, path="/webhook")
    setup_application(app, dp, bot=bot)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
