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
)
from aiogram.enums import ChatMemberStatus, ChatType, ParseMode
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

# Middleware для проверки блокировки пользователя
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

@dp.my_chat_member()
async def handle_block(event: ChatMemberUpdated):
    if event.chat.type == ChatType.PRIVATE:
        user_id = event.from_user.id
        new_status = event.new_chat_member.status
        if new_status == ChatMemberStatus.KICKED:
            db.block_user(user_id, permanent=True)
        elif new_status == ChatMemberStatus.MEMBER:
            db.unblock_user(user_id)

async def check_chats_task():
    while True:
        now = datetime.now()
        long_searches = db.get_users_in_long_search(now - timedelta(minutes=5))
        for user in long_searches:
            db.stop_search(user['id'])
            try:
                await bot.send_message(user['id'], "❌ Поиск автоматически остановлен из-за долгого ожидания", reply_markup=online.builder("🔎 Найти чат"))
            except Exception:
                pass
        
        expired_blocks = db.get_expired_blocks(now)
        for user in expired_blocks:
            db.unblock_user(user['id'])
        
        await asyncio.sleep(180)

@dp.message(Command("unlock"))
async def unlock_user(message: Message):
    if message.from_user.id != DEVELOPER_ID:
        await message.answer("🚫 У вас нет прав для использования этой команды.")
        return

    try:
        user_id = int(message.text.split()[1])  # Получаем ID пользователя из команды
    except (IndexError, ValueError):
        await message.answer("❌ Пожалуйста, укажите корректный Telegram ID пользователя для разблокировки.")
        return

    user = db.get_user_cursor(user_id)
    if not user:
        await message.answer("❌ Пользователь не найден в базе данных.")
        return

    if not user['blocked']:
        await message.answer("❌ Пользователь не заблокирован.")
        return

    db.unblock_user(user_id)
    await message.answer(f"✅ Пользователь с ID {user_id} успешно разблокирован.")

# Остальной код остается без изменений...

# Например, добавьте здесь остальные функции и обработчики

async def on_startup(bot: Bot):
    await bot.set_webhook(f"{WEBHOOK_URL}/webhook")

async def main():
    asyncio.create_task(check_chats_task())

    await bot.set_my_commands([
        BotCommand(command="/start", description="Начать поиск"),
        BotCommand(command="/stop", description="Закончить диалог"),
        BotCommand(command="/next", description="Новый собеседник"),
        BotCommand(command="/search", description="Начать поиск"),
        BotCommand(command="/link", description="Поделиться профилем"),
        BotCommand(command="/interests", description="Настроить интересы"),
        BotCommand(command="/dev", description="Меню разработчика"),
        BotCommand(command="/unlock", description="Разблокировать пользователя")  # Новая команда
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
