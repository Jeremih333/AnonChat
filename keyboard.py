from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

class Online:
    @staticmethod
    def builder(button_text: str) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=button_text, callback_data="search")]
            ]
        )

def gender_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Мужской", callback_data="gender_male"),
                InlineKeyboardButton(text="Женский", callback_data="gender_female")
            ]
        ]
    )

def interests_keyboard(selected_interests: list) -> InlineKeyboardMarkup:
    interests = [
        "Ролевые игры", "Одиночество", "Игры",
        "Аниме", "Мемы", "Флирт", "Музыка",
        "Путешествия", "Фильмы", "Книги",
        "Питомцы", "Спорт"
    ]
    
    keyboard = []
    row = []
    for interest in interests:
        emoji = "✅ " if interest in selected_interests else "⚪️ "
        row.append(
            InlineKeyboardButton(
                text=f"{emoji}{interest}",
                callback_data=f"toggle_{interest}"
            )
        )
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    
    keyboard.append([
        InlineKeyboardButton(text="💾 Сохранить", callback_data="save_interests"),
        InlineKeyboardButton(text="❌ Сбросить", callback_data="reset_interests")
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)
