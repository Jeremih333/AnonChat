# app.py
import asyncio
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
        await callback.message.edit_text("✅ Спасибо за подписку! Теперь вы можете использовать бота.")
        await search_chat(callback.message)
    else:
        await callback.answer("❌ Вы ещё не подписались на канал!", show_alert=True)

@dp.message(Command("stop"))
async def stop_command(message: Message):
    user = db.get_user_cursor(message.from_user.id)
    if user and user["status"] == 2:
        rival_id = user["rid"]
        db.stop_chat(message.from_user.id, rival_id)
        await message.answer(
            "✅ Вы завершили диалог\n\nДля нового поиска нажмите \"🔎 Найти чат\"",
            reply_markup=online.builder("🔎 Найти чат")
        )
        await bot.send_message(rival_id,
            "❌ Диалог завершён\n\nДля нового поиска нажмите \"🔎 Найти чат\"",
            reply_markup=online.builder("🔎 Найти чат")
        )

@dp.message(Command("next"))
async def next_command(message: Message):
    await stop_command(message)
    await search_chat(message)

@dp.message(Command("link"))
async def link_command(message: Message):
    user = db.get_user_cursor(message.from_user.id)
    if user and user["status"] == 2:
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
            await message.answer("✅ Ссылка успешно отправлена!")
        except Exception as e:
            print(f"Ошибка отправки ссылки: {e}")
            await message.answer("❌ Не удалось отправить ссылку")

@dp.message(F.text == "❌ Завершить поиск")
async def stop_search(message: Message):
    user = db.get_user_cursor(message.from_user.id)
    if user and user["status"] == 1:
        db.stop_search(message.from_user.id)
        await message.answer("✅ Поиск остановлен", reply_markup=online.builder("🔎 Найти чат"))

@dp.message(F.text == "❌ Завершить диалог")
async def stop_chat(message: Message):
    await stop_command(message)

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
                if r.type == "emoji"
            ]

            await bot.set_message_reaction(
                chat_id=rival_id,
                message_id=original_msg_id,
                reaction=reaction
            )
        except Exception as e:
            print(f"Ошибка обработки реакции: {e}")

# Важное изменение: добавляем фильтр типа чата
@dp.message(F.chat.type == ChatType.PRIVATE)
async def handler_message(message: Message):
    user = db.get_user_cursor(message.from_user.id)
    if user and user["status"] == 2:
        try:
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

            db.save_message_link(message.from_user.id, message.message_id, sent_msg.message_id)
            db.save_message_link(user["rid"], sent_msg.message_id, message.message_id)

        except Exception as e:
            print(f"Ошибка при пересылке: {e}")

@app.route('/')
def index():
    return "Bot is running!"

@app.route('/webhook', methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_data = request.get_json()
        update = types.Update(**json_data)
        asyncio.run(dp.feed_webhook_update(bot, update))
        return ''
    return 'Invalid content type', 400

async def set_webhook():
    await bot.set_webhook(
        url="YOUR_RENDER_URL/webhook",
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
