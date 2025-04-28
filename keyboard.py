from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

class Online:
    @staticmethod
    def builder(text: str):
        """Создает Reply клавиатуру с одной кнопкой"""
        return InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text=text, callback_data="search")]]
        )

class GenderKeyboard:
    @staticmethod
    def get():
        """Клавиатура выбора пола"""
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="👨 Мужской", callback_data="gender_male"),
                    InlineKeyboardButton(text="👩 Женский", callback_data="gender_female")
                ]
            ]
        )

class InterestsKeyboard:
    INTERESTS_LIST = [
        "Ролевые игры", "Одиночество", "Игры",
        "Аниме", "Мемы", "Флирт", "Музыка",
        "Путешествия", "Фильмы", "Книги",
        "Питомцы", "Спорт"
    ]

    @classmethod
    def get(cls, selected_interests: list):
        """Интерактивная клавиатура выбора интересов"""
        builder = InlineKeyboardBuilder()
        
        # Добавляем кнопки интересов
        for interest in cls.INTERESTS_LIST:
            emoji = "✅" if interest in selected_interests else "⚪"
            builder.button(
                text=f"{emoji} {interest}", 
                callback_data=f"toggle_{interest}"
            )
        
        # Добавляем кнопки управления
        builder.button(text="🔒 Сохранить", callback_data="save_interests")
        builder.button(text="❌ Сбросить", callback_data="reset_interests")
        
        # Форматируем в 2 колонки
        builder.adjust(2, 2, 2, 2, 2, 2, 2)
        return builder.as_markup()

class SubscriptionKeyboard:
    @staticmethod
    def get():
        """Клавиатура для проверки подписки"""
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ Подписаться", url="https://t.me/freedom346"),
                    InlineKeyboardButton(text="🔄 Проверить", callback_data="check_sub")
                ]
            ]
        )

class ReferralKeyboard:
    @staticmethod
    def get(url: str):
        """Клавиатура для реферальной ссылки"""
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="📤 Поделиться", url=f"tg://msg_url?url={url}")]
            ]
        )

class AdminKeyboard:
    @staticmethod
    def get():
        """Клавиатура меню разработчика"""
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🔎 Поиск пользователя", callback_data="dev_find_user")],
                [InlineKeyboardButton(text="🎖 Выдать VIP", callback_data="dev_give_vip")],
                [InlineKeyboardButton(text="🔓 Разблокировать", callback_data="dev_unban")],
                [InlineKeyboardButton(text="📊 Статистика", callback_data="dev_stats")]
            ]
        )

class FeedbackKeyboard:
    @staticmethod
    def get():
        """Клавиатура для оценки собеседника"""
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="👍", callback_data="rate_good"),
                    InlineKeyboardButton(text="👎", callback_data="rate_bad")
                ],
                [InlineKeyboardButton(text="⚠️ Пожаловаться", callback_data="report")]
            ]
        )
