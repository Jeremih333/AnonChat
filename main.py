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

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не найден в переменных окружения!")

WEBHOOK_URL = os.getenv("WEBHOOK_URL", "https://your-service.onrender.com")
PORT = int(os.getenv("PORT", 10000))

bot = Bot(token=TOKEN)
dp = Dispatcher()
db = Database("users.db")

async def is_subscribed(user_id: int) -> bool:
    try:
        member = await bot.get_chat_member("@freedom346", user_id)
        return member.status in {
            ChatMemberStatus.MEMBER,
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.CREATOR
        }
    except Exception as e:
        print(f"Ошибка проверки подписки: {e}")
        return False

def build_gender_kb(prefix: str = "gender") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="👨 Мужской", callback_data=f"{prefix}_male"),
        InlineKeyboardButton(text="👩 Женский", callback_data=f"{prefix}_female")
    ]])

@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    user_id = message.from_user.id
    args = message.text.split()
    
    if len(args) > 1 and args[1].startswith('ref'):
        referrer_id = args[1][3:]
        if referrer_id.isdigit() and int(referrer_id) != user_id:
            await db.increment_referral_count(int(referrer_id))
            user_data = await db.get_user_cursor(int(referrer_id))
            if user_data and user_data["referral_count"] >= 5:
                expiry = datetime.now() + timedelta(days=30)
                await db.activate_vip(int(referrer_id), expiry)

    if not await db.get_user_cursor(user_id):
        await db.new_user(user_id)
        await message.answer("👤 Выберите ваш пол:", reply_markup=build_gender_kb())
        await state.set_state(Form.gender)
    else:
        user_data = await db.get_user_cursor(user_id)
        if not user_data.get("gender") or not user_data.get("age"):
            await restart_registration(message, state)
        else:
            await show_main_menu(message)

async def restart_registration(message: Message, state: FSMContext):
    await message.answer("❌ Завершите регистрацию!\n👤 Выберите ваш пол:", 
                       reply_markup=build_gender_kb())
    await state.set_state(Form.gender)

@dp.callback_query(F.data.startswith("gender_"), Form.gender)
async def process_gender(cq: CallbackQuery, state: FSMContext):
    gender = cq.data.split("_")[1]
    await db.update_gender_age(cq.from_user.id, gender=gender)
    await cq.message.edit_text(f"✅ Пол: {'👨 Мужской' if gender == 'male' else '👩 Женский'}")
    await cq.message.answer("📅 Введите ваш возраст (13-100):")
    await state.set_state(Form.age)

@dp.message(Form.age)
async def process_age(message: Message, state: FSMContext):
    if not message.text.isdigit() or not (13 <= int(message.text) <= 100):
        return await message.answer("❌ Некорректный возраст! Введите число от 13 до 100:")
    
    await db.update_gender_age(message.from_user.id, age=int(message.text))
    await state.clear()
    await show_main_menu(message)

async def show_main_menu(message: Message):
    menu_text = "👋 Добро пожаловать!\n"
    if await db.check_vip_status(message.from_user.id):
        menu_text += "🌟 Ваш VIP статус активен!\n"
    await message.answer(menu_text, reply_markup=online.builder("🔎 Найти чат"))

@dp.message(F.text == "🔎 Найти чат")
async def search_dialog(message: Message):
    user_id = message.from_user.id
    user_data = await db.get_user_cursor(user_id)
    
    if not user_data:
        return await message.answer("❌ Ошибка: пользователь не найден")
    
    if not user_data.get("gender") or not user_data.get("age"):
        return await restart_registration(message, FSMContext)
    
    if not await is_subscribed(user_id):
        return await ask_for_subscription(message)
    
    if await db.check_vip_status(user_id):
        await message.answer("⚙️ Выберите пол для поиска:", 
                           reply_markup=build_gender_kb("vip_filter"))
        await Form.vip_filter.set()
    else:
        await start_search(message)

async def ask_for_subscription(message: Message):
    subscribe_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подписаться", url="https://t.me/freedom346")],
        [InlineKeyboardButton(text="🔄 Проверить подписку", callback_data="check_sub")]
    ])
    await message.answer("📢 Для использования бота необходимо подписаться на наш канал!",
                       reply_markup=subscribe_kb)

async def start_search(message: Message, gender_filter: str = None):
    user_id = message.from_user.id
    try:
        rival = await db.search_vip(user_id, gender_filter) if gender_filter else await db.search(user_id)
        
        if not rival:
            await db.update_status(user_id, 1)
            await message.answer("🔍 Ищем подходящего собеседника...", 
                               reply_markup=online.builder("❌ Отмена"))
        else:
            await db.start_chat(user_id, rival["id"])
            info_text = "🎉 Собеседник найден!"
            if await db.check_vip_status(user_id):
                info_text += f"\n👤 Пол: {'👨 Мужской' if rival['gender'] == 'male' else '👩 Женский'}"
                info_text += f"\n📆 Возраст: {rival['age']}"
            
            await message.answer(info_text, reply_markup=online.builder("❌ Завершить"))
            await bot.send_message(rival["id"], "🎉 Собеседник найден!", 
                                  reply_markup=online.builder("❌ Завершить"))
    except Exception as e:
        print(f"Ошибка поиска: {e}")
        await message.answer("⚠️ Произошла ошибка при поиске. Попробуйте снова.")

@dp.callback_query(F.data.startswith("vip_filter_"))
async def vip_filter_handler(cq: CallbackQuery):
    gender = cq.data.split("_")[2]
    await cq.message.edit_text(f"🔎 Ищем {gender}...")
    await start_search(cq.message, gender)

@dp.callback_query(F.data == "check_sub")
async def check_subscription(cq: CallbackQuery):
    if await is_subscribed(cq.from_user.id):
        await cq.message.edit_text("✅ Подписка подтверждена!")
        await search_dialog(cq.message)
    else:
        await cq.answer("❌ Вы всё ещё не подписаны!", show_alert=True)

@dp.message(Command("stop"))
async def cmd_stop(message: Message):
    user_data = await db.get_user_cursor(message.from_user.id)
    if user_data and user_data["status"] == 2:
        rival_id = user_data["rid"]
        await db.stop_chat(message.from_user.id, rival_id)
        await message.answer("✅ Диалог завершён", 
                           reply_markup=online.builder("🔎 Найти чат"))
        await bot.send_message(rival_id, "⚠️ Собеседник покинул чат", 
                             reply_markup=online.builder("🔎 Найти чат"))

@dp.message(Command("next"))
async def cmd_next(message: Message):
    user_data = await db.get_user_cursor(message.from_user.id)
    if user_data and user_data["status"] == 2:
        rival_id = user_data["rid"]
        await db.stop_chat(message.from_user.id, rival_id)
        await message.answer("✅ Диалог завершён, начинаем новый поиск...")
        await search_dialog(message)
    else:
        await message.answer("❌ Вы не находитесь в активном диалоге")

@dp.message(Command("referral"))
async def cmd_referral(message: Message):
    bot_username = (await bot.get_me()).username
    ref_link = f"https://t.me/{bot_username}?start=ref{message.from_user.id}"
    await message.answer(
        f"📨 Ваша реферальная ссылка:\n{ref_link}\n\n"
        "💎 Пригласите 5 друзей для получения VIP статуса на 30 дней!"
    )

async def setup_bot_commands():
    commands = [
        BotCommand(command="/start", description="Старт"),
        BotCommand(command="/stop", description="Остановить диалог"),
        BotCommand(command="/next", description="Новый собеседник"),
        BotCommand(command="/referral", description="Реферальная система"),
        BotCommand(command="/vip", description="VIP статус")
    ]
    await bot.set_my_commands(commands)

async def webhook_init():
    app = web.Application()
    webhook_handler = SimpleRequestHandler(dp, bot)
    webhook_handler.register(app, path="/webhook")
    setup_application(app, dp, bot=bot)
    
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", PORT).start()

async def main():
    await setup_bot_commands()
    await webhook_init()
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
