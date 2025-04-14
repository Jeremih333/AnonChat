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
PORT = int(os.getenv("PORT", 10000))

# Инициализация бота и диспетчера
bot = Bot(token)
dp = Dispatcher()
db = database("users.db")

# Список интересов с правильной капитализацией
INTERESTS = [
    "Ролевые игры", "Одиночество", "Игры",
    "Аниме", "Мемы", "Флирт", 
    "Музыка", "Путешествия", "Фильмы",
    "Книги", "Питомцы", "Спорт"
]

async def is_subscribed(user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id="@freedom346", user_id=user_id)
        return member.status in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR]
    except Exception:
        return False

def get_interests_keyboard(user_id: int) -> InlineKeyboardMarkup:
    user_interests = db.get_user_interests(user_id) or []
    buttons = []
    
    # Создаем кнопки интересов с отметкой выбранных
    for interest in INTERESTS:
        emoji = "✅ " if interest in user_interests else ""
        buttons.append(
            InlineKeyboardButton(
                text=f"{emoji}{interest}", 
                callback_data=f"interest_{interest}"
            )
        )
    
    # Разбиваем на ряды по 3 кнопки
    keyboard = [buttons[i:i+3] for i in range(0, len(buttons), 3)]
    
    # Добавляем кнопку сброса
    keyboard.append([
        InlineKeyboardButton(
            text="❌ Сбросить интересы", 
            callback_data="reset_interests"
        )
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

@dp.message(Command("interests"))
async def interests_command(message: Message):
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

    await message.answer(
        "Мы попытаемся соединить вас с собеседниками, которые выбрали похожие интересы.\n\n"
        "Выберите ваши интересы:",
        reply_markup=get_interests_keyboard(message.from_user.id)
    )

@dp.callback_query(F.data.startswith("interest_"))
async def toggle_interest(callback: CallbackQuery):
    interest = callback.data.split("_", 1)[1]
    user_id = callback.from_user.id
    
    current_interests = db.get_user_interests(user_id) or []
    
    if interest in current_interests:
        db.remove_interest(user_id, interest)
    else:
        db.add_interest(user_id, interest)
    
    await callback.message.edit_reply_markup(
        reply_markup=get_interests_keyboard(user_id)
    )
    await callback.answer()

@dp.callback_query(F.data == "reset_interests")
async def reset_interests(callback: CallbackQuery):
    db.clear_interests(callback.from_user.id)
    await callback.message.edit_reply_markup(
        reply_markup=get_interests_keyboard(callback.from_user.id)
    )
    await callback.answer("✅ Интересы сброшены!")

# Остальной код без изменений (как в предыдущей версии)
# ... [остальной код остается без изменений] ...

async def on_startup(bot: Bot):
    await bot.set_webhook(f"{WEBHOOK_URL}/webhook")

async def main():
    await bot.set_my_commands([
        BotCommand(command="/start", description="Начать поиск"),
        BotCommand(command="/stop", description="Закончить диалог"),
        BotCommand(command="/next", description="Новый собеседник"),
        BotCommand(command="/link", description="Поделиться профилем"),
        BotCommand(command="/interests", description="Настроить интересы")  # Добавлена новая команда
    ])
    
    # Настройка веб-приложения
    app = web.Application()
    app["bot"] = bot
    
    # Регистрация обработчика вебхуков
    webhook_requests_handler = SimpleRequestHandler(
        dispatcher=dp,
        bot=bot
    )
    webhook_requests_handler.register(app, path="/webhook")
    
    # Настройка приложения
    setup_application(app, dp, bot=bot)
    
    # Установка вебхука при старте
    await on_startup(bot)
    
    # Запуск сервера
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=PORT)
    await site.start()
    
    # Бесконечный цикл
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
