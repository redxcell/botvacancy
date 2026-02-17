"""
Минимальный тестовый бот для проверки callback'ов
Запустите: python test_callbacks.py
"""

import asyncio
import logging
from aiogram import Bot, Dispatcher, Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.storage.memory import MemoryStorage

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ВАЖНО: Замените на свой токен и ID
BOT_TOKEN = "YOUR_BOT_TOKEN"  # ← Вставьте токен
ADMIN_IDS = [123456789]  # ← Вставьте свой Telegram ID

# Инициализация
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
router = Router()


def is_admin(user_id: int) -> bool:
    """Проверка, является ли пользователь админом"""
    return user_id in ADMIN_IDS


def get_test_keyboard() -> InlineKeyboardMarkup:
    """Тестовая клавиатура"""
    keyboard = [
        [
            InlineKeyboardButton(text="Кнопка 1", callback_data="test_1"),
            InlineKeyboardButton(text="Кнопка 2", callback_data="test_2")
        ],
        [
            InlineKeyboardButton(text="Кнопка 3", callback_data="test_3")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


@router.message(Command("test"))
async def cmd_test(message: Message):
    """Тестовая команда"""
    logger.info(f"Команда /test от пользователя {message.from_user.id}")
    
    if not is_admin(message.from_user.id):
        await message.answer(f"❌ Ваш ID: {message.from_user.id}\nВы не админ!")
        logger.warning(f"Пользователь {message.from_user.id} не является админом")
        return
    
    text = f"✅ Вы админ! ID: {message.from_user.id}\n\nНажмите любую кнопку:"
    await message.answer(text, reply_markup=get_test_keyboard())


@router.callback_query(F.data.startswith("test_"))
async def handle_test_callback(callback: CallbackQuery):
    """Обработчик тестовых кнопок"""
    logger.info(f"Callback {callback.data} от пользователя {callback.from_user.id}")
    
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    
    button_num = callback.data.split("_")[1]
    
    await callback.message.edit_text(
        f"✅ Вы нажали кнопку {button_num}!\n\nCallback'и работают правильно!",
        reply_markup=get_test_keyboard()
    )
    await callback.answer(f"Нажата кнопка {button_num}")


async def main():
    """Главная функция"""
    dp.include_router(router)
    
    logger.info("=" * 60)
    logger.info("🧪 ТЕСТОВЫЙ БОТ ЗАПУЩЕН")
    logger.info("=" * 60)
    logger.info(f"Админы: {ADMIN_IDS}")
    logger.info("Отправьте боту команду /test")
    logger.info("=" * 60)
    
    try:
        await dp.start_polling(bot, allowed_updates=["message", "callback_query"])
    finally:
        await bot.session.close()


if __name__ == "__main__":
    # Проверка перед запуском
    if BOT_TOKEN == "YOUR_BOT_TOKEN":
        print("❌ Ошибка: Замените YOUR_BOT_TOKEN на реальный токен бота!")
        print("   Откройте test_callbacks.py и измените BOT_TOKEN")
        exit(1)
    
    if ADMIN_IDS == [123456789]:
        print("⚠️  Предупреждение: Замените 123456789 на свой Telegram ID!")
        print("   Узнать ID можно через бота @userinfobot")
        print()
        input("Нажмите Enter для продолжения или Ctrl+C для отмены...")
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен")
