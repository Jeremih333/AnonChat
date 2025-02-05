import asyncio
import os
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
from aiogram.enums import ChatMemberStatus, ChatType
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

# Импорты из ваших модулей
from database import database
from keyboard import online

# Проверка обязательных переменных окружения
if not (token := os.getenv("TELEGRAM_BOT_TOKEN")):
    raise ValueError("TELEGRAM_BOT_TOKEN не установлен в переменных окружения!")

WEBHOOK_URL = os.getenv("WEBHOOK_URL", "https://your-service-name.onrender.com")
PORT = int(os.getenv("PORT", 10000))  # Render использует порт 10000 по умолчанию

# Инициализация бота и диспетчера
bot = Bot(token)
dp = Dispatcher()
db = database("users.db")

async def is_subscribed(user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id="@freedom346", user_id=user_id)
        return member.status in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR]
    except Exception as e:
        print(f"Ошибка проверки подписки: {e}")
        return False

@dp.message(Command("start"))
async def start_command(message: Message):
    user = db.get_user_cursor(message.from_user.id)
    if not user:
        db.new_user(message.from_user.id)
        await message.answer(
            "👥 Добро пожаловать в Анонимный Чат Бот!\n"
            "🗣 Наш бот предоставляет возможность анонимного общения.\n",
            reply_markup=online.builder("🔎 Найти чат")
        )
    else:
        await search_chat(message)

@dp.message(F.text.regexp(r'https?://\S+|@\w+') | F.caption.regexp(r'https?://\S+|@\w+'))
async def block_links(message: Message):
    await message.delete()
    await message.answer("❌ Отправка ссылок и упоминаний запрещена!")

@dp.message(F.text == "🔎 Найти чат")
async def search_chat(message: Message):
    if not await is_subscribed(message.from_user.id):
        subscribe_markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Подписаться", url="https://t.me/freedom346")],
            [InlineKeyboardButton(text="🔄 Проверить подписку", callback_data="check_sub")]
        ])
        await message.answer(
            "⚠️ Для использования бота необходимо подписаться на наш чат!\n"
            "После подписки нажмите кнопку ниже:",
            reply_markup=subscribe_markup
        )
        return

    user = db.get_user_cursor(message.from_user.id)
    if user:
        rival = db.search(message.from_user.id)

        if not rival:
            await message.answer(
                "🔎 Вы начали поиск собеседника...",
                reply_markup=online.builder("❌ Завершить поиск")
            )
        else:
            db.start_chat(message.from_user.id, rival["id"])
            text = "✅ Собеседник найден!\nЧтобы завершить диалог, нажмите \"❌ Завершить диалог\""
            await message.answer(text, reply_markup=online.builder("❌ Завершить диалог"))
            await bot.send_message(rival["id"], text, reply_markup=online.builder("❌ Завершить диалог"))

@dp.callback_query(F.data == "check_sub")
async def check_subscription(callback: CallbackQuery):
    if await is_subscribed(callback.from_user.id):
        # Удаляем клавиатуру и отправляем новое сообщение
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer("✅ Спасибо за подписку! Теперь вы можете использовать бота.")
        await search_chat(callback.message)
    else:
        await callback.answer("❌ Вы ещё не подписались на канал!", show_alert=True)

# Остальные обработчики остаются без изменений
# ... (stop_command, next_command, link_command и другие)

async def on_startup(bot: Bot):
    await bot.set_webhook(f"{WEBHOOK_URL}/webhook")

async def main():
    await bot.set_my_commands([
        BotCommand(command="/start", description="Начать поиск"),
        BotCommand(command="/stop", description="Закончить диалог"),
        BotCommand(command="/next", description="Новый собеседник"),
        BotCommand(command="/link", description="Поделиться профилем")
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
