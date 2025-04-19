import asyncio
import os
from datetime import datetime, timedelta
from aiogram import Bot, F, Dispatcher
from aiogram.filters import Command, Text
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    BotCommand,
    ChatType,
)
from aiogram.enums import ChatMemberStatus, ParseMode
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

# --- Middleware для проверки блокировки пользователя ---
class BlockedUserMiddleware:
    async def __call__(self, handler, event: Message, data):
        user = db.get_user_cursor(event.from_user.id)
        if user:
            now = datetime.now()
            blocked_until = datetime.fromisoformat(user['blocked_until']) if user['blocked_until'] else None
            if user['blocked'] or (blocked_until and blocked_until > now):
                # При блокировке показываем сообщение с кнопкой "Подать Апелляцию"
                appeal_kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="Подать Апелляцию", callback_data="appeal_start")]
                ])
                await event.answer("🚫 Вы заблокированы и не можете использовать бота!", reply_markup=appeal_kb)
                return
        return await handler(event, data)

dp.message.outer_middleware(BlockedUserMiddleware())

# --- Обработка меню /dev с новыми кнопками ---
@dp.message(Command("dev"))
async def dev_menu(message: Message):
    if message.from_user.id != DEVELOPER_ID:
        return
    stats = {"total_users": "N/A"}
    try:
        db.cursor.execute("SELECT COUNT(*) FROM users")
        stats["total_users"] = db.cursor.fetchone()[0]
    except Exception:
        pass

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Заблокированные пользователи", callback_data="dev_blocked_users")],
        [InlineKeyboardButton(text="Разблокировать", callback_data="dev_unblock_prompt")]
    ])

    await message.answer(
        f"👨‍💻 Меню разработчика\n"
        f"Пользователей в базе: {stats['total_users']}\n"
        "Жалобы направляются сюда автоматически.",
        reply_markup=kb
    )

# --- Список заблокированных пользователей ---
@dp.callback_query(F.data == "dev_blocked_users")
async def show_blocked_users(callback: CallbackQuery):
    if callback.from_user.id != DEVELOPER_ID:
        await callback.answer("Доступ запрещён", show_alert=True)
        return

    blocked_users = db.get_all_blocked_users()
    if not blocked_users:
        await callback.answer("Нет заблокированных пользователей", show_alert=True)
        return

    lines = []
    now = datetime.now()
    for u in blocked_users:
        uid = u['id']
        until = u['blocked_until']
        if until:
            until_dt = datetime.fromisoformat(until)
            remaining = until_dt - now
            if remaining.total_seconds() > 0:
                remain_str = str(remaining).split('.')[0]
            else:
                remain_str = "Истёк"
        else:
            remain_str = "Навсегда"
        lines.append(f"ID: {uid} — Разблокировка: {remain_str}")

    text = "🚫 Заблокированные пользователи:\n" + "\n".join(lines)
    await callback.message.edit_text(text, reply_markup=None)
    await callback.answer()

# --- Запрос ID пользователя для разблокировки ---
@dp.callback_query(F.data == "dev_unblock_prompt")
async def unblock_prompt(callback: CallbackQuery):
    if callback.from_user.id != DEVELOPER_ID:
        await callback.answer("Доступ запрещён", show_alert=True)
        return
    await callback.message.answer("Введите ID пользователя для разблокировки:")
    await callback.answer()
    # Устанавливаем флаг ожидания ID
    dp.current_state(user=callback.from_user.id).set_state("waiting_unblock_id")

from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

class DevUnblockStates(StatesGroup):
    waiting_unblock_id = State()

@dp.message(F.chat.type == ChatType.PRIVATE)
async def unblock_id_handler(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state != "waiting_unblock_id":
        return
    if message.from_user.id != DEVELOPER_ID:
        await message.answer("Доступ запрещён")
        await state.clear()
        return
    try:
        user_id = int(message.text.strip())
    except ValueError:
        await message.answer("Ошибка: ID должен быть числом. Попробуйте ещё раз.")
        return

    user = db.get_user_cursor(user_id)
    if not user or not user['blocked']:
        await message.answer("Пользователь с таким ID не найден или не заблокирован.")
        await state.clear()
        return

    db.unblock_user(user_id)
    await message.answer(f"✅ Пользователь {user_id} успешно разблокирован.")
    await state.clear()

# --- Обработка нажатия кнопки "Подать Апелляцию" у заблокированного пользователя ---
@dp.callback_query(F.data == "appeal_start")
async def appeal_start_handler(callback: CallbackQuery):
    await callback.answer()
    await callback.message.answer(
        "📝 Вы можете написать апелляцию, объяснив, что вы не виноваты в блокировке.\n"
        "Отправьте ваше сообщение, и оно будет направлено разработчику."
    )
    await dp.current_state(user=callback.from_user.id).set_state("waiting_appeal_text")

class AppealStates(StatesGroup):
    waiting_appeal_text = State()

@dp.message(F.chat.type == ChatType.PRIVATE)
async def appeal_text_handler(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state != "waiting_appeal_text":
        return
    # Отправляем апелляцию разработчику с кнопками
    appeal_text = message.text.strip()
    if not appeal_text:
        await message.answer("Пустое сообщение. Пожалуйста, отправьте текст апелляции.")
        return

    appeal_kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Ответить пользователю", callback_data=f"appeal_reply_{message.from_user.id}"),
            InlineKeyboardButton(text="Разблокировать", callback_data=f"appeal_unblock_{message.from_user.id}"),
            InlineKeyboardButton(text="Игнорировать", callback_data=f"appeal_ignore_{message.from_user.id}")
        ]
    ])

    await bot.send_message(
        DEVELOPER_ID,
        f"📩 Апелляция от пользователя {message.from_user.id}:\n\n{appeal_text}",
        reply_markup=appeal_kb
    )
    await message.answer("✅ Ваша апелляция отправлена разработчику.")
    await state.clear()

# --- Обработка кнопок апелляции у разработчика ---
@dp.callback_query(F.data.startswith("appeal_"))
async def appeal_action_handler(callback: CallbackQuery):
    if callback.from_user.id != DEVELOPER_ID:
        await callback.answer("Доступ запрещён", show_alert=True)
        return

    data = callback.data.split('_', 2)
    action = data[1]
    user_id = int(data[2])

    if action == "reply":
        await callback.message.answer(f"Введите ответ для пользователя {user_id}:")
        await dp.current_state(user=callback.from_user.id).set_state(f"waiting_appeal_reply_{user_id}")
        await callback.answer()

    elif action == "unblock":
        db.unblock_user(user_id)
        await callback.answer(f"Пользователь {user_id} разблокирован.")
        await callback.message.edit_reply_markup(reply_markup=None)

    elif action == "ignore":
        await callback.answer("Апелляция проигнорирована")
        await callback.message.edit_reply_markup(reply_markup=None)

# --- Обработка ввода ответа разработчика на апелляцию ---
@dp.message(F.chat.type == ChatType.PRIVATE)
async def appeal_reply_handler(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if not current_state or not current_state.startswith("waiting_appeal_reply_"):
        return
    if message.from_user.id != DEVELOPER_ID:
        await message.answer("Доступ запрещён")
        await state.clear()
        return

    user_id = int(current_state.split('_')[-1])
    reply_text = message.text.strip()
    if not reply_text:
        await message.answer("Пустое сообщение. Пожалуйста, введите текст ответа.")
        return

    try:
        await bot.send_message(user_id, f"📬 Ответ от разработчика:\n{reply_text}")
        await message.answer(f"✅ Ответ отправлен пользователю {user_id}.")
    except Exception:
        await message.answer("❌ Не удалось отправить сообщение пользователю.")
    await state.clear()

# --- Добавление метода в database.py для получения всех заблокированных ---
def get_all_blocked_users(self):
    self.cursor.execute("SELECT * FROM users WHERE blocked = 1")
    return [dict(row) for row in self.cursor.fetchall()]

# Добавляем в класс database:
setattr(database, "get_all_blocked_users", get_all_blocked_users)

# --- Остальной ваш код без изменений ---

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

def get_block_keyboard(user_id: int) -> InlineKeyboardMarkup:
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

# Проверка на доступность команд в группах
async def is_private_chat(message: Message) -> bool:
    return message.chat.type == ChatType.PRIVATE

@dp.message(Command("start"))
async def start_command(message: Message):
    if not await is_private_chat(message):
        await message.answer("🚫 Команды бота недоступны в группах.")
        return

    user = db.get_user_cursor(message.from_user.id)
    
    if user and user.get("status") == 2:  # Проверка, находится ли пользователь в диалоге
        await message.answer("❌ Вы уже находитесь в диалоге.")
        return

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
    if not await is_private_chat(message):
        await message.answer("🚫 Команды бота недоступны в группах.")
        return
    await search_chat(message)

@dp.message(F.text.regexp(r'https?://\S+|@\w+') | F.caption.regexp(r'https?://\S+|@\w+'))
async def block_links(message: Message):
    await message.delete()
    await message.answer("❌ Отправка ссылок и упоминаний запрещена!")

@dp.message(F.text == "🔎 Найти чат")
async def search_chat(message: Message):
    if not await is_private_chat(message):
        await message.answer("🚫 Команды бота недоступны в группах.")
        return

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
            # Уведомление о совпадении интересов
            interests_text = ""
            user_interests = set(user['interests'].split(',')) if isinstance(user['interests'], str) else user['interests']
            rival_interests = set(rival['interests'].split(',')) if isinstance(rival['interests'], str) else rival['interests']
            common_interests = user_interests & rival_interests
            if common_interests:
                interests_text = f" (интересы: {', '.join(common_interests)})"

            db.start_chat(message.from_user.id, rival["id"])
            text = (
                f"Собеседник найден 🐵{interests_text}\n"
                "/next — искать нового собеседника\n"
                "/stop — закончить диалог\n"
                "/interests — добавить интересы поиска\n\n"
                f"<code>{'https://t.me/Anonchatyooubot'}</code>"
            )
            await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=online.builder("❌ Завершить диалог"))
            await bot.send_message(rival["id"], text, parse_mode=ParseMode.HTML, reply_markup=online.builder("❌ Завершить диалог"))

@dp.callback_query(F.data == "check_sub")
async def check_subscription(callback: CallbackQuery):
    if await is_private_chat(callback.message):
        if await is_subscribed(callback.from_user.id):
            await callback.message.edit_text("✅ Спасибо за подписку! Теперь вы можете использовать бота.")
            await search_chat(callback.message)
        else:
            await callback.answer("❌ Вы ещё не подписались на канал!", show_alert=True)

@dp.message(Command("stop"))
async def stop_command(message: Message):
    if not await is_private_chat(message):
        await message.answer("🚫 Команды бота недоступны в группах.")
        return

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
    else:
        await message.answer("✅ Диалог уже завершен.", reply_markup=online.builder("🔎 Найти чат"))

@dp.callback_query(F.data == "rate_good")
async def handle_rate_good(callback: CallbackQuery):
    user_id = callback.from_user.id
    rival_id = db.get_last_rival(user_id)
    if rival_id:
        db.add_rating(rival_id, 1)  # Добавляем положительный рейтинг
        await callback.answer("✅ Спасибо за положительную оценку!")
    else:
        await callback.answer("❌ Не удалось найти собеседника для оценки.", show_alert=True)
    await callback.message.edit_reply_markup(reply_markup=None)

@dp.callback_query(F.data == "rate_bad")
async def handle_rate_bad(callback: CallbackQuery):
    user_id = callback.from_user.id
    rival_id = db.get_last_rival(user_id)
    if rival_id:
        db.add_rating(rival_id, -1)  # Добавляем отрицательный рейтинг
        await callback.answer("❌ Спасибо за отрицательную оценку!")
    else:
        await callback.answer("❌ Не удалось найти собеседника для оценки.", show_alert=True)
    await callback.message.edit_reply_markup(reply_markup=None)

@dp.message(Command("interests"))
async def interests_command(message: Message):
    if not await is_private_chat(message):
        await message.answer("🚫 Команды бота недоступны в группах.")
        return

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

    # Удаляем предыдущее сообщение с интересами, если оно есть
    await message.answer(
        "Выберите ваши интересы для поиска:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )

@dp.callback_query(F.data.startswith("interest_"))
async def interest_handler(callback: CallbackQuery):
    if not await is_private_chat(callback.message):
        await callback.answer("🚫 Команды бота недоступны в группах.")
        return

    interest = callback.data.split("_", 1)[1]
    try:
        db.add_interest(callback.from_user.id, interest)
        await callback.answer(f"✅ Добавлен: {interest}")

        # Удаляем сообщение с выбором интересов
        await callback.message.delete()
    except Exception:
        await callback.answer("❌ Ошибка обновления")

@dp.callback_query(F.data == "reset_interests")
async def reset_interests(callback: CallbackQuery):
    if not await is_private_chat(callback.message):
        await callback.answer("🚫 Команды бота недоступны в группах.")
        return

    db.clear_interests(callback.from_user.id)
    await callback.answer("✅ Интересы сброшены")

@dp.message(Command("next"))
async def next_command(message: Message):
    if not await is_private_chat(message):
        await message.answer("🚫 Команды бота недоступны в группах.")
        return

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
        
        # Убираем кнопку завершения диалога и показываем кнопку поиска
        await message.answer("✅ Диалог завершен.", reply_markup=online.builder("🔎 Найти чат"))
    else:
        await message.answer("🔍 Начинаем поиск собеседника...")
        await search_chat(message)

@dp.message(Command("link"))
async def link_command(message: Message):
    if not await is_private_chat(message):
        await message.answer("🚫 Команды бота недоступны в группах.")
        return

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
        except Exception:
            await message.answer("❌ Ошибка отправки")

@dp.message(F.text == "❌ Завершить поиск")
async def stop_search(message: Message):
    if not await is_private_chat(message):
        await message.answer("🚫 Команды бота недоступны в группах.")
        return

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
            reply_to_message_id = None
            if message.reply_to_message:
                reply_to_message_id = db.get_rival_message_id(message.from_user.id, message.reply_to_message.message_id)

            sent_msg = None
            if message.photo:
                sent_msg = await bot.send_photo(
                    user["rid"],
                    message.photo[-1].file_id,
                    caption=message.caption,
                    reply_to_message_id=reply_to_message_id
                )
            elif message.text:
                sent_msg = await bot.send_message(
                    user["rid"],
                    message.text,
                    reply_to_message_id=reply_to_message_id
                )
            elif message.voice:
                sent_msg = await bot.send_audio(
                    user["rid"],
                    message.voice.file_id,
                    caption=message.caption,
                    reply_to_message_id=reply_to_message_id
                )
            elif message.video_note:
                sent_msg = await bot.send_video_note(
                    user["rid"],
                    message.video_note.file_id,
                    reply_to_message_id=reply_to_message_id
                )
            elif message.sticker:
                sent_msg = await bot.send_sticker(
                    user["rid"],
                    message.sticker.file_id,
                    reply_to_message_id=reply_to_message_id
                )
            elif message.animation:  # Обработка GIF
                sent_msg = await bot.send_animation(
                    user["rid"],
                    message.animation.file_id,
                    caption=message.caption,
                    reply_to_message_id=reply_to_message_id
                )
            elif message.video:  # Обработка видео
                sent_msg = await bot.send_video(
                    user["rid"],
                    message.video.file_id,
                    caption=message.caption,
                    reply_to_message_id=reply_to_message_id
                )
            elif message.document:  # Обработка документов
                sent_msg = await bot.send_document(
                    user["rid"],
                    message.document.file_id,
                    caption=message.caption,
                    reply_to_message_id=reply_to_message_id
                )

            if sent_msg:
                db.save_message_link(message.from_user.id, message.message_id, sent_msg.message_id)
                db.save_message_link(user["rid"], sent_msg.message_id, message.message_id)

                content = message.text or message.caption or ''
                db.save_message(message.from_user.id, user["rid"], content)

        except Exception as e:
            print(f"Ошибка пересылки сообщения: {e}")

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
