import asyncio
import os
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
from aiogram.enums import ChatMemberStatus
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiohttp import web

from database import Database
from keyboard import online

class Form(StatesGroup):
    gender = State()
    age = State()
    vip_filter = State()

# Проверка токена
if not (token := os.getenv("TELEGRAM_BOT_TOKEN")):
    raise ValueError("TELEGRAM_BOT_TOKEN не установлен!")

# Конфигурация вебхука
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "https://your-service.onrender.com")
PORT = int(os.getenv("PORT", 10000))

# Инициализация бота и БД
bot = Bot(token)
dp = Dispatcher()
db = Database("users.db")

async def is_subscribed(user_id: int) -> bool:
    """Проверка подписки на канал"""
    try:
        member = await bot.get_chat_member("@freedom346", user_id)
        return member.status in [
            ChatMemberStatus.MEMBER,
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.CREATOR
        ]
    except Exception:
        return False

def gender_keyboard(prefix: str = "filter") -> InlineKeyboardMarkup:
    """Клавиатура выбора пола"""
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="👨 Мужской", callback_data=f"{prefix}_male"),
        InlineKeyboardButton(text="👩 Женский", callback_data=f"{prefix}_female")
    ]])

@dp.message(Command("start"))
async def start_command(message: Message, state: FSMContext):
    """Обработчик команды /start"""
    args = message.text.split()
    user = db.get_user_cursor(message.from_user.id)
    
    # Обработка реферальной ссылки
    if len(args) > 1 and args[1].startswith('ref'):
        referrer_id = args[1][3:]
        if referrer_id.isdigit() and int(referrer_id) != message.from_user.id:
            db.increment_referral_count(int(referrer_id))
            referrer = db.get_user_cursor(int(referrer_id))
            if referrer and referrer['referral_count'] >= 5:
                expiry = datetime.now() + timedelta(days=30)
                db.activate_vip(int(referrer_id), expiry)

    # Логика регистрации
    if not user:
        db.new_user(message.from_user.id)
        await message.answer("👤 Выберите ваш пол:", reply_markup=gender_keyboard("gender"))
        await state.set_state(Form.gender)
    else:
        if not user.get('gender') or not user.get('age'):
            await start_registration(message, state)
        else:
            await main_menu(message)

async def start_registration(message: Message, state: FSMContext):
    """Перезапуск регистрации"""
    await message.answer(
        "❌ Завершите регистрацию!\n👤 Выберите ваш пол:", 
        reply_markup=gender_keyboard("gender")
    )
    await state.set_state(Form.gender)

@dp.callback_query(F.data.startswith("gender_"), Form.gender)
async def process_gender(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора пола"""
    gender = callback.data.split('_')[1]
    db.update_gender_age(callback.from_user.id, gender, None)
    await callback.message.edit_text(
        f"✅ Пол: {'👨 Мужской' if gender == 'male' else '👩 Женский'}"
    )
    await request_age(callback.message)
    await state.set_state(Form.age)

async def request_age(message: Message):
    """Запрос возраста"""
    await message.answer("📅 Введите ваш возраст (13-100):")

@dp.message(Form.age)
async def process_age(message: Message, state: FSMContext):
    """Обработка ввода возраста"""
    if not message.text.isdigit() or not (13 <= int(message.text) <= 100):
        await message.answer("❌ Некорректный возраст! Введите число от 13 до 100:")
        return
    
    age = int(message.text)
    db.update_gender_age(message.from_user.id, None, age)
    await state.clear()
    await main_menu(message)
    await message.answer("✅ Регистрация завершена!")

async def main_menu(message: Message):
    """Главное меню"""
    text = "👋 Добро пожаловать!\n"
    if db.check_vip_status(message.from_user.id):
        text += "🌟 VIP статус активен!\n"
    await message.answer(text, reply_markup=online.builder("🔎 Найти чат"))

@dp.message(F.text == "🔎 Найти чат")
async def search_chat(message: Message):
    """Поиск собеседника"""
    user = db.get_user_cursor(message.from_user.id)
    
    if not user.get('gender') or not user.get('age'):
        await start_registration(message, FSMContext)
        return
    
    if not await is_subscribed(message.from_user.id):
        subscribe_markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Подписаться", url="https://t.me/freedom346")],
            [InlineKeyboardButton(text="🔄 Проверить", callback_data="check_sub")]
        ])
        await message.answer(
            "⚠️ Подпишитесь на канал для использования бота!", 
            reply_markup=subscribe_markup
        )
        return
    
    if db.check_vip_status(message.from_user.id):
        await message.answer(
            "⚙️ Выберите пол для поиска:", 
            reply_markup=gender_keyboard("vip_filter")
        )
        await Form.vip_filter.set()
    else:
        await start_search(message)

async def start_search(message: Message, gender_filter: str = None):
    """Запуск поиска"""
    user_id = message.from_user.id
    rival = db.search_vip(user_id, gender_filter) if gender_filter else db.search(user_id)
    
    if not rival:
        db.update_status(user_id, 1)
        await message.answer(
            "🔎 Поиск собеседника...", 
            reply_markup=online.builder("❌ Отмена")
        )
    else:
        db.start_chat(user_id, rival['id'])
        text = "✅ Собеседник найден!"
        if db.check_vip_status(user_id):
            text += f"\n👤 Пол: {'👨 Мужской' if rival['gender'] == 'male' else '👩 Женский'}"
            text += f"\n📅 Возраст: {rival['age']}"
        
        await message.answer(text, reply_markup=online.builder("❌ Завершить"))
        await bot.send_message(
            rival['id'], 
            "✅ Собеседник найден!", 
            reply_markup=online.builder("❌ Завершить")
        )

@dp.callback_query(F.data.startswith("vip_filter_"))
async def process_vip_filter(callback: CallbackQuery):
    """Обработка VIP фильтра"""
    gender = callback.data.split('_')[2]
    await callback.message.edit_text(f"🔎 Ищем {gender}...")
    await start_search(callback.message, gender)

@dp.callback_query(F.data == "check_sub")
async def check_subscription(callback: CallbackQuery):
    """Проверка подписки"""
    if await is_subscribed(callback.from_user.id):
        await callback.message.edit_text("✅ Подписка подтверждена!")
        await search_chat(callback.message)
    else:
        await callback.answer("❌ Вы не подписаны!", show_alert=True)

@dp.message(Command("stop"))
async def stop_command(message: Message):
    """Остановка диалога"""
    user = db.get_user_cursor(message.from_user.id)
    if user and user['status'] == 2:
        rival_id = user['rid']
        db.stop_chat(message.from_user.id, rival_id)
        await message.answer(
            "✅ Диалог завершен", 
            reply_markup=online.builder("🔎 Найти чат")
        )
        await bot.send_message(
            rival_id, 
            "❌ Собеседник вышел", 
            reply_markup=online.builder("🔎 Найти чат")
        )

@dp.message(Command("referral"))
async def referral_command(message: Message):
    """Реферальная система"""
    ref_link = f"https://t.me/{(await bot.get_me()).username}?start=ref{message.from_user.id}"
    await message.answer(
        f"🔗 Реферальная ссылка:\n{ref_link}\n\n"
        "Пригласите 5 друзей для получения VIP статуса на 1 месяц!"
    )

async def main():
    """Запуск бота"""
    # Настройка команд бота
    await bot.set_my_commands([
        BotCommand(command="/start", description="Начать"),
        BotCommand(command="/stop", description="Стоп"),
        BotCommand(command="/referral", description="Рефералка"),
        BotCommand(command="/vip", description="VIP статус")
    ])
    
    # Конфигурация вебхука
    app = web.Application()
    webhook_requests_handler = SimpleRequestHandler(dp, bot)
    webhook_requests_handler.register(app, path="/webhook")
    setup_application(app, dp, bot=bot)
    
    # Запуск сервера
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    
    # Бесконечный цикл
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
