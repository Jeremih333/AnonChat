import asyncio
import os
from datetime import datetime, timedelta
from aiogram import Bot, F, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    BotCommand,
    MessageReactionUpdated,
    ReactionTypeEmoji,
    ChatMemberUpdated,
)
from aiogram.enums import ChatMemberStatus, ChatType, ParseMode
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiohttp import web
from database import Database
from keyboard import online, gender_keyboard, interests_keyboard

if not (token := os.getenv("TELEGRAM_BOT_TOKEN")):
    raise ValueError("TELEGRAM_BOT_TOKEN не установлен!")

WEBHOOK_URL = os.getenv("WEBHOOK_URL", "https://your-service-name.onrender.com")
PORT = int(os.getenv("PORT", 10000))

bot = Bot(token)
dp = Dispatcher()
db = Database("users.db")

DEVELOPER_ID = 1040929628

# Состояния для регистрации и админки
class RegistrationStates(StatesGroup):
    GENDER = State()
    AGE = State()

class DevCommands(StatesGroup):
    USER_ACTION = State()
    VIP_ACTION = State()
    UNBAN_ACTION = State()

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
        # Проверка долгого поиска
        long_searches = db.get_users_in_long_search(now - timedelta(minutes=5))
        for user in long_searches:
            db.stop_search(user['id'])
            try:
                await bot.send_message(user['id'], "❌ Поиск автоматически остановлен из-за долгого ожидания", 
                                      reply_markup=online.builder("🔎 Найти чат"))
            except Exception:
                pass
        
        # Проверка истечения блокировок
        expired_blocks = db.get_expired_blocks(now)
        for user in expired_blocks:
            db.unblock_user(user['id'])
        
        # Проверка истечения VIP
        expired_vips = db.get_expired_vips(now)
        for user in expired_vips:
            await bot.send_message(user['id'], "💎 Ваш VIP статус истек! Пригласите друзей для продления /ref")
        
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

async def is_private_chat(message: Message) -> bool:
    return message.chat.type == ChatType.PRIVATE

@dp.message(Command("dev"))
async def dev_menu(message: Message, state: FSMContext):
    if message.from_user.id != DEVELOPER_ID:
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔎 Поиск пользователя", callback_data="dev_find_user")],
        [InlineKeyboardButton(text="🎖 Выдать VIP", callback_data="dev_give_vip")],
        [InlineKeyboardButton(text="🔓 Разблокировать", callback_data="dev_unban")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="dev_stats")]
    ])
    
    await message.answer("👨💻 Меню разработчика:", reply_markup=keyboard)
    await state.set_state(DevCommands.USER_ACTION)

@dp.callback_query(F.data.startswith("dev_"))
async def dev_actions(callback: CallbackQuery, state: FSMContext):
    action = callback.data.split("_")[1]
    
    if action == "give_vip":
        await callback.message.answer("Введите ID пользователя и количество дней через пробел:")
        await state.set_state(DevCommands.VIP_ACTION)
    
    elif action == "unban":
        await callback.message.answer("Введите ID пользователя для разблокировки:")
        await state.set_state(DevCommands.UNBAN_ACTION)
    
    elif action == "stats":
        stats = {
            "total_users": db.get_total_users(),
            "active_vips": db.get_active_vips_count(),
            "banned_users": db.get_banned_users_count()
        }
        await callback.message.answer(
            f"📊 Статистика бота:\n"
            f"👥 Всего пользователей: {stats['total_users']}\n"
            f"💎 Активных VIP: {stats['active_vips']}\n"
            f"🚫 Заблокированных: {stats['banned_users']}"
        )
    
    await callback.answer()

@dp.message(DevCommands.VIP_ACTION)
async def handle_vip_action(message: Message, state: FSMContext):
    try:
        user_id, days = map(int, message.text.split())
        db.add_vip_days(user_id, days)
        await message.answer(f"✅ Пользователю {user_id} выдан VIP на {days} дней")
        await bot.send_message(user_id, f"🎉 Вам выдан VIP статус на {days} дней!")
    except:
        await message.answer("❌ Неверный формат. Пример: 123456 7")
    await state.clear()

@dp.message(DevCommands.UNBAN_ACTION)
async def handle_unban_action(message: Message, state: FSMContext):
    try:
        user_id = int(message.text)
        db.unblock_user(user_id)
        await message.answer(f"✅ Пользователь {user_id} разблокирован")
        await bot.send_message(user_id, "🔓 Ваша блокировка снята!")
    except:
        await message.answer("❌ Неверный ID пользователя")
    await state.clear()

@dp.message(Command("start"))
async def start_command(message: Message, state: FSMContext):
    if not await is_private_chat(message):
        await message.answer("🚫 Команды бота недоступны в группах.")
        return

    # Обработка реферальной ссылки
    referrer_id = None
    if len(message.text.split()) > 1:
        ref_code = message.text.split()[1]
        if ref_code.startswith('ref'):
            referrer_id = int(ref_code[3:])

    user = db.get_user_cursor(message.from_user.id)
    
    if user and user.get("status") == 2:
        await message.answer("❌ Вы уже находитесь в диалоге.")
        return

    if not user:
        db.new_user(message.from_user.id)
        if referrer_id and db.get_user_cursor(referrer_id):
            db.handle_referral(message.from_user.id, referrer_id)
            await bot.send_message(referrer_id, "🎉 По вашей ссылке зарегистрировался новый пользователь! +1 день VIP")

    user = db.get_user_cursor(message.from_user.id)
    
    if not user['gender'] or not user['age']:
        await message.answer("📝 Для использования бота необходимо пройти регистрацию!")
        await message.answer("Выберите ваш пол:", reply_markup=gender_keyboard())
        await state.set_state(RegistrationStates.GENDER)
        return

    await message.answer(
        "👥 Добро пожаловать в Анонимный Чат Бот!\n"
        "💎 Приглашайте друзей и получайте VIP статус /ref\n\n"
        "🗣 Начните общение:",
        reply_markup=online.builder("🔎 Найти чат")
    )

@dp.message(RegistrationStates.GENDER)
async def process_gender(message: Message, state: FSMContext):
    gender = message.text.lower()
    if gender not in ['мужской', 'женский']:
        await message.answer("❌ Пожалуйста, выберите пол используя кнопки ниже")
        return
    
    await state.update_data(gender=gender)
    await message.answer("📅 Введите ваш возраст:")
    await state.set_state(RegistrationStates.AGE)

@dp.message(RegistrationStates.AGE)
async def process_age(message: Message, state: FSMContext):
    try:
        age = int(message.text)
        if not 12 <= age <= 100:
            raise ValueError
    except ValueError:
        await message.answer("❌ Пожалуйста, введите корректный возраст (число от 12 до 100)")
        return
    
    data = await state.get_data()
    db.update_user_info(message.from_user.id, data['gender'], age)
    await state.clear()
    
    # Реклама VIP после регистрации
    await message.answer(
        "✅ Регистрация завершена!\n\n"
        "💎 Получите VIP статус для:\n"
        "➢ Поиска по полу собеседника\n"
        "➢ Приоритета в поиске\n"
        "➢ Эксклюзивных функций\n\n"
        "Используйте /ref для приглашения друзей!",
        reply_markup=online.builder("🔎 Найти чат")
    )

@dp.message(Command("ref"))
async def ref_command(message: Message):
    code = db.get_referral_code(message.from_user.id)
    ref_link = f"https://t.me/{(await bot.get_me()).username}?start=ref{code}"
    await message.answer(
        f"🔗 Ваша реферальная ссылка:\n{ref_link}\n\n"
        "💎 За каждого приглашенного друга вы получаете:\n"
        "➢ +1 день VIP статуса\n"
        "➢ Приоритет в поиске собеседника\n"
        "➢ Особый статус в профиле",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="📤 Поделиться", url=f"tg://msg_url?url={ref_link}")
        ]])
    )

@dp.message(Command("vip"))
async def vip_info(message: Message):
    if db.get_vip_status(message.from_user.id):
        vip_until = datetime.fromisoformat(db.get_user_cursor(message.from_user.id)['vip_until'])
        days_left = (vip_until - datetime.now()).days
        await message.answer(
            f"🌟 Ваш VIP статус активен ещё {days_left} дней!\n"
            f"Дата окончания: {vip_until.strftime('%d.%m.%Y %H:%M')}\n\n"
            "💎 Продлите статус приглашая друзей /ref"
        )
    else:
        await message.answer(
            "💎 VIP статус открывает новые возможности:\n\n"
            "➢ Поиск по полу собеседника\n"
            "➢ Приоритет в очереди на поиск\n"
            "➢ Расширенные настройки профиля\n\n"
            "🎁 Получить VIP можно приглашая друзей /ref\n"
            "Или обратитесь к администратору"
        )

@dp.message(Command("search"))
async def search_command(message: Message):
    if not await is_private_chat(message):
        await message.answer("🚫 Команды бота недоступны в группах.")
        return
    await search_chat(message)

@dp.message(F.text == "🔎 Найти чат")
async def search_chat(message: Message):
    if not await is_private_chat(message):
        await message.answer("🚫 Команды бота недоступны в группах.")
        return

    # Проверка подписки
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
            # Реклама VIP для ускорения поиска
            if not db.get_vip_status(message.from_user.id):
                await message.answer(
                    "⏳ Обычный поиск может занять больше времени...\n"
                    "💎 Получите VIP статус для приоритета в поиске /vip"
                )
            
            await message.answer(
                "🔎 Ищем собеседника...",
                reply_markup=online.builder("❌ Завершить поиск")
            )
        else:
            interests_text = ""
            user_interests = user['interests'].split(',') if user['interests'] else []
            rival_interests = rival['interests'].split(',') if rival['interests'] else []
            common_interests = list(set(user_interests) & set(rival_interests))
            if common_interests:
                interests_text = f" (совпадение интересов: {', '.join(common_interests)})"

            db.start_chat(message.from_user.id, rival["id"])
            text = (
                f"👤 Собеседник найден {interests_text}\n"
                "💬 Теперь вы можете общаться анонимно\n\n"
                "/next — новый собеседник\n"
                "/stop — закончить диалог\n"
                "/interests — изменить интересы"
            )
            markup = online.builder("❌ Завершить диалог")
            await message.answer(text, reply_markup=markup)
            await bot.send_message(rival["id"], text, reply_markup=markup)

@dp.message(Command("interests"))
async def interests_command(message: Message):
    if not await is_private_chat(message):
        await message.answer("🚫 Команды бота недоступны в группах.")
        return

    user = db.get_user_cursor(message.from_user.id)
    current_interests = user['interests'].split(',') if user and user['interests'] else []
    
    await message.answer(
        "🎯 Выберите ваши интересы для поиска собеседника:",
        reply_markup=interests_keyboard(current_interests)
    )

@dp.callback_query(F.data.startswith("toggle_"))
async def toggle_interest(callback: CallbackQuery):
    interest = callback.data.split("_", 1)[1]
    user = db.get_user_cursor(callback.from_user.id)
    current = user['interests'].split(',') if user and user['interests'] else []
    
    if interest in current:
        current.remove(interest)
    else:
        current.append(interest)
    
    db._update_interests(callback.from_user.id, current)
    await callback.message.edit_reply_markup(
        reply_markup=interests_keyboard(current)
    )

@dp.callback_query(F.data == "save_interests")
async def save_interests(callback: CallbackQuery):
    await callback.message.delete()
    await callback.answer("✅ Интересы сохранены")
    await callback.message.answer(
        "🎯 Настройки поиска обновлены!\n"
        "💎 VIP пользователи получают больше совпадений /vip"
    )

@dp.callback_query(F.data == "reset_interests")
async def reset_interests(callback: CallbackQuery):
    db.clear_interests(callback.from_user.id)
    await callback.answer("✅ Интересы сброшены")
    await callback.message.edit_reply_markup(
        reply_markup=interests_keyboard([])
    )

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
                "Диалог завершен. Оцените собеседника:\n"
                "💎 Хотите больше возможностей? Получите VIP /vip",
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
        BotCommand(command="/start", description="Начать работу"),
        BotCommand(command="/stop", description="Закончить диалог"),
        BotCommand(command="/next", description="Новый собеседник"),
        BotCommand(command="/search", description="Начать поиск"),
        BotCommand(command="/interests", description="Настроить интересы"),
        BotCommand(command="/ref", description="Реферальная система"),
        BotCommand(command="/vip", description="VIP статус"),
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
