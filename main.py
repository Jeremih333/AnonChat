import asyncio
import os
from aiogram import Bot, F, Dispatcher
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
from aiohttp import web
from database import Database  # Измененный импорт

# Проверка обязательных переменных окружения
if not (token := os.getenv("TELEGRAM_BOT_TOKEN")):
    raise ValueError("TELEGRAM_BOT_TOKEN не установлен!")

WEBHOOK_URL = os.getenv("WEBHOOK_URL", "https://your-service-name.onrender.com")
PORT = int(os.getenv("PORT", 10000))

# Инициализация бота и диспетчера
bot = Bot(token)
dp = Dispatcher()
db = Database("users.db")  # Исправленная инициализация

async def is_subscribed(user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id="@freedom346", user_id=user_id)
        return member.status in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR]
    except Exception as e:
        print(f"Ошибка проверки подписки: {e}")
        return False

@dp.message(Command("start"))
async def start_command(message: Message):
    if not db.get_user(message.from_user.id):
        db.add_user(message.from_user.id)
        await message.answer(
            "👥 Добро пожаловать в Анонимный Чат Бот!\n"
            "🗣 Наш бот предоставляет возможность анонимного общения.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="🔎 Найти чат", callback_data="search")
            ]])
        )
    else:
        await search_chat(message)

@dp.callback_query(F.data == "search")
async def search_handler(callback: CallbackQuery):
    await search_chat(callback.message)

async def search_chat(message: Message):
    if not await is_subscribed(message.from_user.id):
        subscribe_markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Подписаться", url="https://t.me/freedom346")],
            [InlineKeyboardButton(text="🔄 Проверить подписку", callback_data="check_sub")]
        ])
        await message.answer(
            "⚠️ Для использования бота необходимо подписаться на наш чат!",
            reply_markup=subscribe_markup
        )
        return

    # Добавляем пользователя в очередь поиска
    db.update_user(message.from_user.id, {"searching": 1})
    
    # Поиск соперника
    rival_id = db.find_rival(message.from_user.id)
    
    if rival_id:
        # Связываем пользователей
        db.create_chat(message.from_user.id, rival_id)
        text = "✅ Собеседник найден!\nЧтобы завершить диалог, нажмите \"❌ Завершить диалог\""
        await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="❌ Завершить диалог", callback_data="stop")
        ]]))
        await bot.send_message(rival_id, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="❌ Завершить диалог", callback_data="stop")
        ]]))
    else:
        await message.answer(
            "🔎 Ищем собеседника...",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="❌ Завершить поиск", callback_data="stop_search")
            ]])
        )

@dp.callback_query(F.data == "check_sub")
async def check_subscription(callback: CallbackQuery):
    if await is_subscribed(callback.from_user.id):
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer("✅ Теперь вы можете использовать бота!")
        await search_chat(callback.message)
    else:
        await callback.answer("❌ Вы ещё не подписались!", show_alert=True)

@dp.callback_query(F.data == "stop")
async def stop_chat(callback: CallbackQuery):
    chat = db.get_chat(callback.from_user.id)
    if chat:
        db.delete_chat(chat['id'])
        rival_id = chat['user1'] if chat['user1'] != callback.from_user.id else chat['user2']
        await callback.message.answer("❌ Диалог завершен")
        await bot.send_message(rival_id, "❌ Собеседник покинул диалог")

async def on_startup(bot: Bot):
    await bot.set_webhook(f"{WEBHOOK_URL}/webhook")

async def main():
    await bot.set_my_commands([
        BotCommand(command="/start", description="Начать поиск"),
        BotCommand(command="/stop", description="Закончить диалог")
    ])
    
    app = web.Application()
    webhook_requests_handler = SimpleRequestHandler(dp, bot)
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
