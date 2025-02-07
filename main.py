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

class Form(StatesGroup):
    gender = State()
    age = State()
    vip_filter = State()

# Инициализация окружения
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "https://your-service.onrender.com")
PORT = int(os.getenv("PORT", 10000))

bot = Bot(token=TOKEN)
dp = Dispatcher()
db = Database("users.db")

#region Utils
def main_keyboard() -> InlineKeyboardMarkup:
    """Основная клавиатура"""
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🔎 Найти чат", callback_data="search"),
        InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")
    ]])

def cancel_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура отмены"""
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")
    ]])

async def is_subscribed(user_id: int) -> bool:
    """Проверка подписки на канал"""
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
    """Клавиатура выбора пола"""
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="👨 Мужской", callback_data=f"{prefix}_male"),
        InlineKeyboardButton(text="👩 Женский", callback_data=f"{prefix}_female")
    ]])

def subscribe_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для подписки"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подписаться", url="https://t.me/freedom346")],
        [InlineKeyboardButton(text="🔄 Проверить подписку", callback_data="check_sub")]
    ])
#endregion

#region Handlers
@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    """Обработчик команды /start"""
    user_id = message.from_user.id
    args = message.text.split()
    
    # Обработка реферальной ссылки
    if len(args) > 1 and args[1].startswith('ref'):
        referrer_id = args[1][3:]
        if referrer_id.isdigit() and int(referrer_id) != user_id:
            await db.increment_referral_count(int(referrer_id))
            user_data = await db.get_user(int(referrer_id))
            if user_data and user_data.referral_count >= 5:
                expiry = datetime.now() + timedelta(days=30)
                await db.activate_vip(int(referrer_id), expiry)

    user_data = await db.get_user(user_id)
    if not user_data:
        await db.new_user(user_id)
        await message.answer("👤 Выберите ваш пол:", reply_markup=build_gender_kb())
        await state.set_state(Form.gender)
    else:
        if not user_data.gender or not user_data.age:
            await restart_registration(message, state)
        else:
            # Автоматический старт поиска для существующих пользователей
            await message.answer("♻️ Возобновляем поиск...")
            await start_search(message)

@dp.callback_query(F.data.startswith("gender_"), Form.gender)
async def process_gender(cq: CallbackQuery, state: FSMContext):
    """Обработка выбора пола"""
    gender = cq.data.split("_")[1]
    await db.update_user(cq.from_user.id, gender=gender)
    await cq.message.edit_text(f"✅ Пол: {'👨 Мужской' if gender == 'male' else '👩 Женский'}")
    await cq.message.answer("📅 Введите ваш возраст (13-100):")
    await state.set_state(Form.age)

@dp.message(Form.age)
async def process_age(message: Message, state: FSMContext):
    """Обработка ввода возраста"""
    if not message.text.isdigit() or not (13 <= int(message.text) <= 100):
        return await message.answer("❌ Некорректный возраст! Введите число от 13 до 100:")
    
    await db.update_user(message.from_user.id, age=int(message.text))
    await state.clear()
    await show_main_menu(message)

@dp.callback_query(F.data == "search")
async def search_handler(cq: CallbackQuery):
    """Обработка поиска"""
    user_id = cq.from_user.id
    user_data = await db.get_user(user_id)
    
    if not await is_subscribed(user_id):
        return await cq.message.answer(
            "📢 Для использования бота необходимо подписаться на наш канал!",
            reply_markup=subscribe_keyboard()
        )
    
    if await db.check_vip_status(user_id):
        await cq.message.answer("⚙️ Выберите пол для поиска:", reply_markup=build_gender_kb("vip_filter"))
        await cq.answer()
    else:
        await start_search(cq.message)

@dp.callback_query(F.data.startswith("vip_filter_"))
async def vip_filter_handler(cq: CallbackQuery):
    """Обработка VIP фильтра"""
    gender = cq.data.split("_")[2]
    await cq.message.edit_text(f"🔎 Ищем {gender}...")
    await start_search(cq.message, gender)

@dp.callback_query(F.data == "check_sub")
async def check_subscription(cq: CallbackQuery):
    """Проверка подписки"""
    if await is_subscribed(cq.from_user.id):
        await cq.message.edit_text("✅ Подписка подтверждена!")
        await search_handler(cq)
    else:
        await cq.answer("❌ Вы всё ещё не подписаны!", show_alert=True)

@dp.callback_query(F.data == "cancel")
async def cancel_handler(cq: CallbackQuery):
    """Обработка отмены"""
    user_data = await db.get_user(cq.from_user.id)
    if user_data:
        if user_data.status == 1:
            await db.update_user(cq.from_user.id, status=0)
            await cq.message.edit_text("❌ Поиск отменён")
        elif user_data.status == 2:
            await db.stop_chat(cq.from_user.id, user_data.rid)
            await cq.message.edit_text("✅ Диалог завершён")
    await cq.answer()

@dp.message(Command("stop"))
async def cmd_stop(message: Message):
    """Остановка диалога/поиска"""
    user_data = await db.get_user(message.from_user.id)
    if user_data:
        if user_data.status == 1:
            await db.update_user(message.from_user.id, status=0)
            await message.answer("❌ Поиск отменён", reply_markup=main_keyboard())
        elif user_data.status == 2:
            await db.stop_chat(message.from_user.id, user_data.rid)
            await message.answer("✅ Диалог завершён", reply_markup=main_keyboard())
            await bot.send_message(user_data.rid, "⚠️ Собеседник покинул чат", reply_markup=main_keyboard())

@dp.message(Command("next"))
async def cmd_next(message: Message):
    """Новый собеседник"""
    user_data = await db.get_user(message.from_user.id)
    if user_data and user_data.status == 2:
        await db.stop_chat(message.from_user.id, user_data.rid)
        await message.answer("♻️ Ищем нового собеседника...")
        await start_search(message)
    else:
        await message.answer("❌ Вы не в диалоге")

@dp.message(Command("referral"))
async def cmd_referral(message: Message):
    """Реферальная система"""
    bot_username = (await bot.get_me()).username
    ref_link = f"https://t.me/{bot_username}?start=ref{message.from_user.id}"
    await message.answer(
        f"📨 Ваша реферальная ссылка:\n{ref_link}\n\n"
        "💎 Пригласите 5 друзей для получения VIP статуса на 30 дней!"
    )

@dp.message(Command("vip"))
async def cmd_vip(message: Message):
    """Информация о VIP статусе"""
    user_data = await db.get_user(message.from_user.id)
    if not user_data:
        return await message.answer("❌ Пользователь не найден")
    
    if user_data.vip and user_data.vip_expiry > datetime.now():
        expiry_date = user_data.vip_expiry.strftime("%d.%m.%Y %H:%M")
        await message.answer(f"🌟 Ваш VIP статус активен до: {expiry_date}")
    else:
        await message.answer("❌ У вас нет активного VIP статуса")
#endregion

#region Helpers
async def restart_registration(message: Message, state: FSMContext):
    """Перезапуск регистрации"""
    await message.answer("❌ Завершите регистрацию!\n👤 Выберите ваш пол:", 
                     reply_markup=build_gender_kb())
    await state.set_state(Form.gender)

async def show_main_menu(message: Message):
    """Главное меню"""
    menu_text = "👋 Добро пожаловать!\n"
    if await db.check_vip_status(message.from_user.id):
        menu_text += "🌟 Ваш VIP статус активен!\n"
    await message.answer(menu_text, reply_markup=main_keyboard())

async def start_search(message: Message, gender_filter: str = None):
    """Начало поиска"""
    user_id = message.from_user.id
    try:
        user_data = await db.get_user(user_id)
        if user_data.status == 2:
            return await message.answer("⚠️ Вы уже в диалоге!")

        rival = await db.search_vip(user_id, gender_filter) if gender_filter else await db.search(user_id)
        
        if not rival:
            await db.update_user(user_id, status=1)
            await message.answer("🔍 Ищем подходящего собеседника...", reply_markup=cancel_keyboard())
        else:
            await db.start_chat(user_id, rival.id)
            info_text = "🎉 Собеседник найден!"
            if await db.check_vip_status(user_id):
                info_text += f"\n👤 Пол: {'👨 Мужской' if rival.gender == 'male' else '👩 Женский'}"
                info_text += f"\n📆 Возраст: {rival.age}"
            
            await message.answer(info_text, reply_markup=cancel_keyboard())
            await bot.send_message(rival.id, "🎉 Собеседник найден!", reply_markup=cancel_keyboard())
    except Exception as e:
        print(f"Ошибка поиска: {e}")
        await message.answer("⚠️ Произошла ошибка при поиске. Попробуйте снова.")
#endregion

#region Setup
async def setup_bot_commands():
    """Настройка команд бота"""
    commands = [
        BotCommand(command="/start", description="Старт/поиск"),
        BotCommand(command="/stop", description="Остановить диалог/поиск"),
        BotCommand(command="/next", description="Новый собеседник"),
        BotCommand(command="/referral", description="Реферальная система"),
        BotCommand(command="/vip", description="VIP статус")
    ]
    await bot.set_my_commands(commands)

async def webhook_init():
    """Инициализация вебхука"""
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
#endregion
