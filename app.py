# app.py
import asyncio
from aiogram import Bot, Dispatcher, types
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
from flask import Flask, request
from database import database
from keyboard import online

app = Flask(__name__)
token = "6753939702:AAFWaHJQrNSb48b2YCWnMXDUNmf_yn9IAvg"

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

# Добавлен недостающий обработчик search_chat
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

# Остальные обработчики остаются без изменений...

@dp.message_reaction()
async def handle_reaction(event: MessageReactionUpdated):
    if event.old_reaction == event.new_reaction:
        return

    user = db.get_user_cursor(event.user.id)
    if user and user["status"] == 2 and event.new_reaction:
        rival_id = user["rid"]
        try:
            original_msg_id = db.get_rival_message_id(event.user.id, event.message_id)
            if not original_msg_id:
                return

            reaction = [
                ReactionTypeEmoji(emoji=r.emoji)
                for r in event.new_reaction
                if isinstance(r, ReactionTypeEmoji)
            ]

            await bot.set_message_reaction(
                chat_id=rival_id,
                message_id=original_msg_id,
                reaction=reaction
            )
        except Exception as e:
            print(f"Ошибка обработки реакции: {e}")

@app.route('/webhook', methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_data = request.get_json()
        update = types.Update(**json_data)
        asyncio.run(dp.process_update(update))
        return ''
    return 'Invalid content type', 400

async def set_webhook():
    await bot.set_webhook(
        url="YOUR_RENDER_URL/webhook",  # Замените на реальный URL
        drop_pending_updates=True
    )

async def main():
    await bot.set_my_commands([
        BotCommand(command="/start", description="Начать поиск"),
        BotCommand(command="/stop", description="Закончить диалог"),
        BotCommand(command="/next", description="Новый собеседник"),
        BotCommand(command="/link", description="Поделиться профилем")
    ])
    await set_webhook()

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(main())
    app.run(host='0.0.0.0', port=5000)
