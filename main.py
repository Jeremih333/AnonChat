import asyncio
import os
import sqlite3
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
from database import database
from keyboard import online

if not (token := os.getenv("TELEGRAM_BOT_TOKEN")):
    raise ValueError("TELEGRAM_BOT_TOKEN не установлен!")

WEBHOOK_URL = os.getenv("WEBHOOK_URL", "https://your-service-name.onrender.com")
PORT = int(os.getenv("PORT", 10000))

bot = Bot(token)
dp = Dispatcher()
db = database("users.db")

async def is_subscribed(user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id="@freedom346", user_id=user_id)
        return member.status in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR]
    except Exception:
        return False

@dp.message(Command("start"))
async def start_command(message: Message):
    try:
        user = db.get_user_cursor(message.from_user.id)
    except sqlite3.OperationalError as e:
        if "no such column" in str(e):
            db._create_tables()
            db._migrate_database()
            user = None
        else:
            raise
    
    if not user:
        db.new_user(message.from_user.id)
        await message.answer(
            "👥 Добро пожаловать в Анонимный Чат Бот!\n"
            "🗣 Наш бот предоставляет возможность анонимного общения.",
            reply_markup=online.builder("🔎 Найти чат")
        )
    else:
        await search_chat(message)

@dp.message(Command("search"))
async def search_command(message: Message):
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
            "⚠️ Для использования бота необходимо подписаться на наш чат!",
            reply_markup=subscribe_markup
        )
        return

    user = db.get_user_cursor(message.from_user.id)
    if user:
        rival = db.search(message.from_user.id)

        if not rival:
            await message.answer(
                "🔎 Ищем собеседника...",
                reply_markup=online.builder("❌ Завершить поиск")
            )
        else:
            db.start_chat(message.from_user.id, rival["id"])
            text = (
                "Собеседник найден 🐵\n"
                "/next — искать нового собеседника\n"
                "/stop — закончить диалог\n"
                "/interests — добавить интересы поиска\n\n"
                f"<code>{'https://t.me/Anonchatyooubot'}</code>"
            )
            await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=online.builder("❌ Завершить диалог"))
            await bot.send_message(rival["id"], text, parse_mode=ParseMode.HTML, reply_markup=online.builder("❌ Завершить диалог"))

@dp.callback_query(F.data == "check_sub")
async def check_subscription(callback: CallbackQuery):
    if await is_subscribed(callback.from_user.id):
        await callback.message.edit_text("✅ Спасибо за подписку! Теперь вы можете использовать бота.")
        await search_chat(callback.message)
    else:
        await callback.answer("❌ Вы ещё не подписались на канал!", show_alert=True)

@dp.message(Command("stop"))
async def stop_command(message: Message):
    user = db.get_user_cursor(message.from_user.id)
    if user and user.get("status") == 2:
        rival_id = user["rid"]
        db.stop_chat(message.from_user.id, rival_id)
        
        feedback_markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="👍", callback_data="rate_good"),
             InlineKeyboardButton(text="👎", callback_data="rate_bad")],
            [InlineKeyboardButton(text="⚠️ Пожаловаться", callback_data="report")]
        ])
        
        await message.answer(
            "Диалог завершен.\nОставьте мнение о собеседнике:",
            reply_markup=feedback_markup
        )
        
        await bot.send_message(
            rival_id,
            "Собеседник закончил диалог 😞\n"
            f"<code>{'https://t.me/Anonchatyooubot'}</code>",
            parse_mode=ParseMode.HTML
        )

@dp.message(Command("interests"))
async def interests_command(message: Message):
    interests = [
        "Ролевые игры", "Одиночество", "Игры", 
        "Аниме", "Мемы", "Флирт", "Музыка", 
        "Путешествия", "Фильмы", "Книги", 
        "Питомцы", "Спорт"
    ]
    buttons = [
        [InlineKeyboardButton(text=interest, callback_data=f"interest_{interest}")] 
        for interest in interests
    ]
    buttons.append([InlineKeyboardButton(text="❌ Сбросить интересы", callback_data="reset_interests")])
    
    await message.answer(
        "Выберите ваши интересы для поиска:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )

@dp.callback_query(F.data.startswith("interest_"))
async def interest_handler(callback: CallbackQuery):
    interest = callback.data.split("_", 1)[1]
    try:
        db.add_interest(callback.from_user.id, interest)
        await callback.answer(f"✅ Добавлен: {interest}")
    except Exception:
        await callback.answer("❌ Ошибка обновления")

@dp.callback_query(F.data == "reset_interests")
async def reset_interests(callback: CallbackQuery):
    db.clear_interests(callback.from_user.id)
    await callback.answer("✅ Интересы сброшены")

@dp.message(Command("next"))
async def next_command(message: Message):
    user = db.get_user_cursor(message.from_user.id)
    if user and user.get("status") == 2:
        rival_id = user["rid"]
        db.stop_chat(message.from_user.id, rival_id)
        
        feedback_markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="👍", callback_data="rate_good"),
             InlineKeyboardButton(text="👎", callback_data="rate_bad")],
            [InlineKeyboardButton(text="⚠️ Пожаловаться", callback_data="report")]
        ])
        
        await message.answer(
            "Ищем нового собеседника...\nОставьте мнение о предыдущем собеседнике:",
            reply_markup=feedback_markup
        )
        
        await bot.send_message(
            rival_id,
            "Собеседник начал новый поиск 🔄\n"
            f"<code>{'https://t.me/Anonchatyooubot'}</code>",
            parse_mode=ParseMode.HTML
        )
    await search_chat(message)

@dp.message(Command("link"))
async def link_command(message: Message):
    user = db.get_user_cursor(message.from_user.id)
    if user and user.get("status") == 2:
        try:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text="👤 Профиль собеседника",
                    url=f"tg://user?id={message.from_user.id}"
                )]
            ])

            await bot.send_message(
                chat_id=user["rid"],
                text="🔗 Ваш собеседник поделился ссылкой:",
                reply_markup=keyboard
            )
            await message.answer("✅ Ссылка отправлена!")
        except Exception as e:
            await message.answer("❌ Ошибка отправки")

@dp.message(F.text == "❌ Завершить поиск")
async def stop_search(message: Message):
    user = db.get_user_cursor(message.from_user.id)
    if user and user.get("status") == 1:
        db.stop_search(message.from_user.id)
        await message.answer("✅ Поиск остановлен", reply_markup=online.builder("🔎 Найти чат"))
    else:
        await message.answer("❌ Активный поиск не найден")

@dp.message(F.text == "❌ Завершить диалог")
async def stop_chat(message: Message):
    await stop_command(message)

@dp.message_reaction()
async def handle_reaction(event: MessageReactionUpdated):
    if event.old_reaction == event.new_reaction:
        return

    user = db.get_user_cursor(event.user.id)
    if user and user.get("status") == 2 and event.new_reaction:
        rival_id = user["rid"]
        try:
            original_msg_id = db.get_rival_message_id(event.user.id, event.message_id)
            if not original_msg_id:
                return

            reaction = [
                ReactionTypeEmoji(emoji=r.emoji)
                for r in event.new_reaction
                if r.type == "emoji"
            ]

            await bot.set_message_reaction(
                chat_id=rival_id,
                message_id=original_msg_id,
                reaction=reaction
            )
        except Exception as e:
            print(f"Ошибка обработки реакции: {e}")

@dp.message(F.chat.type == ChatType.PRIVATE)
async def handler_message(message: Message):
    user = db.get_user_cursor(message.from_user.id)
    if user and user.get("status") == 2:
        try:
            sent_msg = None
            if message.photo:
                sent_msg = await bot.send_photo(user["rid"], message.photo[-1].file_id, caption=message.caption)
            elif message.text:
                sent_msg = await bot.send_message(user["rid"], message.text)
            elif message.voice:
                sent_msg = await bot.send_audio(user["rid"], message.voice.file_id, caption=message.caption)
            elif message.video_note:
                sent_msg = await bot.send_video_note(user["rid"], message.video_note.file_id)
            elif message.sticker:
                sent_msg = await bot.send_sticker(user["rid"], message.sticker.file_id)

            if sent_msg:
                db.save_message_link(message.from_user.id, message.message_id, sent_msg.message_id)
                db.save_message_link(user["rid"], sent_msg.message_id, message.message_id)

        except Exception as e:
            print(f"Ошибка пересылки сообщения: {e}")

async def on_startup(bot: Bot):
    await bot.set_webhook(f"{WEBHOOK_URL}/webhook")

async def main():
    await bot.set_my_commands([
        BotCommand(command="/start", description="Начать поиск"),
        BotCommand(command="/stop", description="Закончить диалог"),
        BotCommand(command="/next", description="Новый собеседник"),
        BotCommand(command="/search", description="Начать поиск"),
        BotCommand(command="/link", description="Поделиться профилем"),
        BotCommand(command="/interests", description="Настроить интересы")
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
