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
    ChatMemberUpdated,
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

def get_block_keyboard(user_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Навсегда", callback_data=f"block_forever_{user_id}"),
            InlineKeyboardButton(text="Год", callback_data=f"block_year_{user_id}"),
            InlineKeyboardButton(text="Месяц", callback_data=f"block_month_{user_id}")
        ],
        [
            InlineKeyboardButton(text="Неделя", callback_data=f"block_week_{user_id}"),
            InlineKeyboardButton(text="День", callback_data=f"block_day_{user_id}"),
            InlineKeyboardButton(text="Игнорировать", callback_data=f"ignore_{user_id}")
        ]
    ])

@dp.callback_query(F.data == "report")
async def handle_report(callback: CallbackQuery):
    # Берем последнего собеседника из БД, а не из статуса
    last_rival_id = db.get_last_rival(callback.from_user.id)
    if not last_rival_id:
        await callback.answer("❌ Не удалось определить собеседника для жалобы", show_alert=True)
        return

    messages = db.get_chat_log(callback.from_user.id, last_rival_id, limit=10)
    log_text = "\n".join([f"{m['timestamp']} — {m['content']}" for m in reversed(messages)]) or "Пустой чат"

    report_msg = (
        f"🚨 Жалоба от пользователя {callback.from_user.id}\n"
        f"На пользователя {last_rival_id}\n"
        f"Лог последних сообщений:\n```\n{log_text}\n```"
    )
    try:
        await bot.send_message(
            DEVELOPER_ID,
            report_msg,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_block_keyboard(last_rival_id)
        )
        await callback.answer("✅ Жалоба отправлена")
        # Удаляем кнопки оценки и жалобы у пользователя
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        await callback.answer("❌ Ошибка отправки жалобы", show_alert=True)

@dp.callback_query(F.data.startswith("block_"))
async def handle_block_action(callback: CallbackQuery):
    parts = callback.data.split('_')
    action = parts[1]
    user_id = int(parts[2])
    
    durations = {
        'forever': None,
        'year': timedelta(days=365),
        'month': timedelta(days=30),
        'week': timedelta(weeks=1),
        'day': timedelta(days=1)
    }
    
    duration = durations.get(action)
    block_until = datetime.now() + duration if duration else None
    db.block_user(user_id, block_until=block_until)
    
    await callback.answer(f"✅ Пользователь {user_id} заблокирован")
    await callback.message.edit_reply_markup(reply_markup=None)

@dp.callback_query(F.data.startswith("ignore_"))
async def handle_ignore(callback: CallbackQuery):
    user_id = int(callback.data.split('_')[1])
    await callback.answer("🚫 Жалоба проигнорирована")
    await callback.message.edit_reply_markup(reply_markup=None)

# --- Остальные обработчики (start, search, stop, next, rate_good, rate_bad и т.д.) ---
# Пример обработчика stop_command с кнопками оценки и жалобы:

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
        
        for user_id in [message.from_user.id, rival_id]:
            await bot.send_message(
                user_id,
                "Диалог завершен.\nОставьте мнение о собеседнике:\n"
                f"<code>{'https://t.me/Anonchatyooubot'}</code>",
                parse_mode=ParseMode.HTML,
                reply_markup=feedback_markup
            )

# Обработчики оценки (rate_good, rate_bad) берут last_rival из БД аналогично

@dp.callback_query(F.data == "rate_good")
async def handle_rate_good(callback: CallbackQuery):
    user = db.get_user_cursor(callback.from_user.id)
    if user and user.get("status") == 0:
        last_rival_id = db.get_last_rival(callback.from_user.id)
        if last_rival_id:
            db.add_rating(last_rival_id, 1)
            await callback.answer("✅ Вы поставили положительную оценку")
            await callback.message.edit_reply_markup()
        else:
            await callback.answer("❌ Не удалось определить собеседника для оценки", show_alert=True)
    else:
        await callback.answer("❌ Оценивать можно только после завершения диалога", show_alert=True)

@dp.callback_query(F.data == "rate_bad")
async def handle_rate_bad(callback: CallbackQuery):
    user = db.get_user_cursor(callback.from_user.id)
    if user and user.get("status") == 0:
        last_rival_id = db.get_last_rival(callback.from_user.id)
        if last_rival_id:
            db.add_rating(last_rival_id, -1)
            await callback.answer("✅ Вы поставили негативную оценку")
            await callback.message.edit_reply_markup()
        else:
            await callback.answer("❌ Не удалось определить собеседника для оценки", show_alert=True)
    else:
        await callback.answer("❌ Оценивать можно только после завершения диалога", show_alert=True)

# --- Здесь остальные ваши обработчики без изменений ---

async def is_subscribed(user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id="@freedom346", user_id=user_id)
        return member.status in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR]
    except Exception:
        return False

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
