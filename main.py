import asyncio
import os
from datetime import datetime, timedelta
from aiogram import Bot, F, Dispatcher
from aiogram.filters import Command
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    BotCommand,
    ParseMode,
)
from aiogram.enums import ChatMemberStatus, ChatType
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web
from database import database
from keyboard import online

if not (token := os.getenv("TELEGRAM_BOT_TOKEN")):
    raise ValueError("TELEGRAM_BOT_TOKEN не установлен!")

WEBHOOK_URL = os.getenv("WEBHOOK_URL", "https://your-service-name.onrender.com")
PORT = int(os.getenv("PORT", 10000))

bot = Bot(token)
dp = Dispatcher()
db = database("users.db")

DEVELOPER_ID = 1040929628

class BlockedUserMiddleware:
    async def __call__(self, handler, event: Message, data):
        user = db.get_user_cursor(event.from_user.id)
        if user:
            now = datetime.now()
            blocked_until = datetime.fromisoformat(user['blocked_until']) if user['blocked_until'] else None
            if user['blocked'] or (blocked_until and blocked_until > now):
                await event.answer("🚫 Вы заблокированы и не можете использовать бота!")
                return
        return await handler(event, data)

dp.message.outer_middleware(BlockedUserMiddleware())

@dp.message(Command("dev"))
async def dev_menu(message: Message):
    if message.from_user.id == DEVELOPER_ID:
        blocked_users = db.get_blocked_users()
        blocked_list = "\n".join([f"ID: {user['id']}, до: {user['blocked_until']}" for user in blocked_users]) or "Нет заблокированных пользователей."
        
        await message.answer(
            f"👨‍💻 Меню разработчика\n"
            f"Заблокированные пользователи:\n{blocked_list}\n"
            "Используйте кнопку ниже для разблокировки."
        )
        await message.answer("Выберите действие:", reply_markup=get_dev_keyboard())

def get_dev_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Заблокированные пользователи", callback_data="view_blocked_users")],
        [InlineKeyboardButton(text="Разблокировать", callback_data="unblock_user")]
    ])

@dp.callback_query(F.data == "view_blocked_users")
async def view_blocked_users(callback: CallbackQuery):
    blocked_users = db.get_blocked_users()
    blocked_list = "\n".join([f"ID: {user['id']}, до: {user['blocked_until']}" for user in blocked_users]) or "Нет заблокированных пользователей."
    await callback.message.edit_text(f"Заблокированные пользователи:\n{blocked_list}")

@dp.callback_query(F.data == "unblock_user")
async def unblock_user(callback: CallbackQuery):
    await callback.message.edit_text("Введите ID пользователя для разблокировки:")
    dp.message.outer_middleware(BlockedUserMiddleware())
    dp.register_message_handler(handle_unblock_user, state="unblocking")

async def handle_unblock_user(message: Message):
    if message.from_user.id != DEVELOPER_ID:
        return
    try:
        user_id = int(message.text)
        db.unblock_user(user_id)
        await message.answer(f"✅ Пользователь {user_id} разблокирован.")
    except ValueError:
        await message.answer("❌ Пожалуйста, введите корректный ID пользователя.")

@dp.message(F.text == "Подать Аппеляцию")
async def appeal_request(message: Message):
    user = db.get_user_cursor(message.from_user.id)
    if user and user['blocked']:
        await message.answer("📝 Вы можете написать свою аппеляцию:")
        dp.register_message_handler(handle_appeal, state="appealing")

async def handle_appeal(message: Message):
    if message.from_user.id == message.from_user.id:
        appeal_text = message.text
        await bot.send_message(
            DEVELOPER_ID,
            f"📩 Аппеляция от пользователя {message.from_user.id}:\n{appeal_text}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Ответить пользователю", callback_data=f"reply_{message.from_user.id}")],
                [InlineKeyboardButton(text="Разблокировать", callback_data=f"unblock_{message.from_user.id}")],
                [InlineKeyboardButton(text="Игнорировать", callback_data=f"ignore_{message.from_user.id}")]
            ])
        )
        await message.answer("✅ Ваша аппеляция отправлена разработчику.")

@dp.callback_query(F.data.startswith("reply_"))
async def reply_to_appeal(callback: CallbackQuery):
    user_id = int(callback.data.split("_")[1])
    await callback.message.answer(f"Ответ для пользователя {user_id}:")
    dp.register_message_handler(lambda msg: handle_reply(msg, user_id), state="replying")

async def handle_reply(message: Message, user_id: int):
    await bot.send_message(user_id, message.text)
    await message.answer("✅ Ответ отправлен пользователю.")

@dp.callback_query(F.data.startswith("unblock_"))
async def unblock_appeal(callback: CallbackQuery):
    user_id = int(callback.data.split("_")[1])
    db.unblock_user(user_id)
    await bot.send_message(user_id, "✅ Вы были разблокированы.")
    await callback.answer("✅ Пользователь разблокирован.")

@dp.callback_query(F.data.startswith("ignore_"))
async def ignore_appeal(callback: CallbackQuery):
    await callback.answer("🚫 Аппеляция проигнорирована.")

async def on_startup(bot: Bot):
    await bot.set_webhook(f"{WEBHOOK_URL}/webhook")

async def main():
    await bot.set_my_commands([
        BotCommand(command="/start", description="Начать поиск"),
        BotCommand(command="/stop", description="Закончить диалог"),
        BotCommand(command="/next", description="Новый собеседник"),
        BotCommand(command="/search", description="Начать поиск"),
        BotCommand(command="/link", description="Поделиться профилем"),
        BotCommand(command="/interests", description="Настроить интересы"),
        BotCommand(command="/dev", description="Меню разработчика")
    ])

    app = web.Application()
    app["bot"] = bot

    webhook_requests_handler = SimpleRequestHandler(
        dispatcher=dp,
        bot=bot
    )
    webhook_requests_handler.register(app, path="/webhook")

    setup_application(app, dp, bot=bot)
    await on_startup(bot)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=PORT)
    await site.start()

    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
