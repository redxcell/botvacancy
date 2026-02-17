"""
Telegram бот для канала @vakhtasever
Автоматическое размещение объявлений о работе
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, ChatMemberUpdated
from aiogram.enums import ChatMemberStatus
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage


from config import config
from database import db
from admin_panel import admin_router, ADMIN_IDS

# ====== НАСТРОЙКА ЛОГИРОВАНИЯ ======
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format=config.LOG_FORMAT,
    handlers=[
        logging.FileHandler(config.LOG_FILE, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ====== ИНИЦИАЛИЗАЦИЯ ======
storage = MemoryStorage()
bot = Bot(token=config.BOT_TOKEN)
dp = Dispatcher(storage=storage)
router = Router()

# ====== FSM СОСТОЯНИЯ ======
class UserStates(StatesGroup):
    waiting_unsubscribe_reason = State()

# ====== УТИЛИТЫ ======

async def check_subscription(user_id: int) -> bool:
    """Проверка подписки пользователя на канал"""
    try:
        member = await bot.get_chat_member(chat_id=config.CHANNEL_CHAT_ID, user_id=user_id)
        return member.status in [
            ChatMemberStatus.MEMBER,
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.CREATOR
        ]
    except Exception as e:
        logger.error(f"Ошибка проверки подписки пользователя {user_id}: {e}")
        return False


def check_banned_words(text: str) -> bool:
    """Проверка текста на запрещенные слова"""
    text_lower = text.lower()
    for word in config.BANNED_WORDS:
        if word in text_lower:
            logger.warning(f"Найдено запрещенное слово: {word}")
            return True
    return False


def validate_ad_start(text: str) -> Optional[str]:
    """
    Проверка начала объявления на соответствие разрешенным фразам
    Возвращает: 'resume', 'vacancy' или None
    """
    text_lower = text.lower().strip()

    # Проверка резюме
    for phrase in config.RESUME_PHRASES:
        if text_lower.startswith(phrase):
            return 'resume'

    # Проверка вакансий
    for phrase in config.VACANCY_PHRASES:
        if text_lower.startswith(phrase):
            return 'vacancy'

    return None





# ====== ОБРАБОТЧИКИ КОМАНД ======

@router.message(CommandStart())
async def cmd_start(message: Message):
    """Обработчик команды /start"""
    # Регистрируем пользователя в БД
    db.add_user(
        tg_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        last_name=message.from_user.last_name
    )

    # Логируем событие
    db.add_log(
        log_type="start",
        message=f"Пользователь @{message.from_user.username} запустил бота",
        tg_id=message.from_user.id
    )

    await message.answer(
        config.WELCOME_MESSAGE.format(
            channel_id=config.CHANNEL_ID,
            discussion_group=config.DISCUSSION_GROUP,
            admin_username=config.ADMIN_USERNAME
        )
    )
    logger.info(f"Пользователь {message.from_user.id} (@{message.from_user.username}) запустил бота")


@router.message(Command("rules"))
async def cmd_rules(message: Message):
    """Обработчик команды /rules"""

    # Формируем список фраз для резюме
    resume_list = "\n".join([f"• «{phrase}»" for phrase in config.RESUME_PHRASES])

    # Формируем список фраз для вакансий
    vacancy_list = "\n".join([f"• «{phrase}»" for phrase in config.VACANCY_PHRASES])

    rules_text = f"""Правила размещения объявлений в канале {config.CHANNEL_ID}

Уважаемые подписчики!

Чтобы ваше объявление (резюме или вакансия) было автоматически опубликовано в канале «Водители, Машинисты, Работа, Вахта» ({config.CHANNEL_ID}), обязательно соблюдайте следующие правила:

1. Обязательное условие — подписка на канал
Перед отправкой объявления вы должны быть подписаны на канал {config.CHANNEL_ID}. Бот автоматически проверяет подписку. Если вы не подписаны, бот попросит вас подписаться и не примет объявление.

2. Как отправить объявление
Отправьте одно текстовое сообщение боту t.me/DriverVakhtaBot. Фото, файлы и ссылки прикреплять нельзя.

3. Начало объявления
Ваше сообщение обязательно должно начинаться с одной из следующих фраз:

Для соискателей (резюме):
{resume_list}

Для работодателей (вакансии):
{vacancy_list}

Важно: фраза должна быть в начале сообщения, без лишних слов перед ней.

4. Содержание объявления
После стартовой фразы кратко и чётко укажите всю необходимую информацию:

Если вы соискатель (ищете работу):
• ФИО
• специальность/разряд
• стаж работы
• ключевые навыки (например: опыт работы с КАМАЗом, категория С, Е)
• регион поиска работы (город/область)
• контакты для связи (телефон, Telegram и т. д.)

Если вы работодатель (ищете сотрудника):
• должность
• тип спецтехники
• регион работы (город/область, вахта)
• условия работы (зарплата, график, жильё, питание и т. д.)
• контакты для откликов (телефон, имя контактного лица, Telegram и т. д.)

5. Что запрещено
• отправка фото, видео, документов или ссылок в объявлении
• спам, реклама, нецензурная лексика
• объявления, не соответствующие тематике канала
• объявления без стартовой фразы из п. 3
• оскорбления, угрозы, дискриминационные высказывания

6. Ограничения
• Длина текста: в пределах ограничений Telegram
• Количество объявлений: неограниченное
• Редактирование: после отправки объявление нельзя изменить или отозвать

7. Помощь и поддержка
Если у вас остались вопросы или возникли проблемы: обратитесь к админу канала: t.me/{config.ADMIN_USERNAME}"""

    await message.answer(rules_text)
    logger.info(f"Пользователь {message.from_user.id} запросил правила")


# ====== ОБРАБОТЧИКИ МЕДИАФАЙЛОВ ======

@router.message(F.photo | F.video | F.document | F.audio | F.voice | F.sticker | F.video_note | F.animation)
async def handle_media(message: Message):
    """Обработчик медиафайлов - отклонение"""
    await message.answer(config.MEDIA_REJECTION_MESSAGE)
    logger.info(f"Пользователь {message.from_user.id} отправил медиафайл")


# ====== ОБРАБОТЧИК ТЕКСТОВЫХ СООБЩЕНИЙ ======

@router.message(F.text)
async def handle_text_message(message: Message, state: FSMContext):
    """Главный обработчик текстовых сообщений (объявлений)"""

    # Игнорируем неизвестные команды
    if message.text.startswith('/'):
        if message.text not in ['/start', '/rules']:
            await message.answer(config.UNKNOWN_COMMAND_MESSAGE)
        return

    # Проверка на пустое сообщение
    if not message.text or not message.text.strip():
        await message.answer(config.EMPTY_MESSAGE_ERROR)
        return

    user_id = message.from_user.id
    username = message.from_user.username
    ad_text = message.text.strip()

    logger.info(f"Получено объявление от пользователя {user_id} (@{username})")

    # Шаг 1: Проверка подписки на канал
    is_subscribed = await check_subscription(user_id)
    if not is_subscribed:
        await message.answer(
            config.NO_SUBSCRIPTION_MESSAGE.format(channel_id=config.CHANNEL_ID)
        )
        logger.info(f"Пользователь {user_id} не подписан на канал")
        return

    # Шаг 2: Проверка на запрещенные слова
    if check_banned_words(ad_text):
        rejection_reason = "Использование запрещенных слов (нецензурная лексика)"

        # Сохраняем отклоненное объявление
        db.add_ad(
            tg_id=user_id,
            username=username,
            ad_text=ad_text,
            ad_type="unknown",
            status="rejected",
            rejection_reason=rejection_reason
        )

        # Логируем отклонение
        db.add_log(
            log_type="ad_rejected",
            message=f"Объявление от @{username} отклонено: {rejection_reason}",
            tg_id=user_id,
            details=ad_text[:100]
        )

        await message.answer(
            config.REJECTION_MESSAGE.format(admin_username=config.ADMIN_USERNAME)
        )
        return

    # Шаг 3: Проверка начальной фразы
    ad_type = validate_ad_start(ad_text)
    if not ad_type:
        rejection_reason = "Объявление не начинается с разрешенной фразы"

        # Сохраняем отклоненное объявление
        db.add_ad(
            tg_id=user_id,
            username=username,
            ad_text=ad_text,
            ad_type="unknown",
            status="rejected",
            rejection_reason=rejection_reason
        )

        # Логируем отклонение
        db.add_log(
            log_type="ad_rejected",
            message=f"Объявление от @{username} отклонено: {rejection_reason}",
            tg_id=user_id,
            details=ad_text[:100]
        )

        await message.answer(
            config.REJECTION_MESSAGE.format(admin_username=config.ADMIN_USERNAME)
        )
        return

    # Шаг 4: Определение хештега и публикация
    hashtag = config.RESUME_HASHTAG if ad_type == "resume" else config.VACANCY_HASHTAG

    try:
        post_text = f"{ad_text}\n\n{hashtag}"
        sent_message = await bot.send_message(
            chat_id=config.CHANNEL_CHAT_ID,
            text=post_text
        )

        # Сохраняем объявление в БД
        db.add_ad(
            tg_id=user_id,
            username=username,
            ad_text=ad_text,
            ad_type=ad_type,
            status="published",
            message_id=sent_message.message_id
        )

        # Логируем успех
        db.add_log(
            log_type="ad_published",
            message=f"Объявление от @{username} опубликовано ({ad_type})",
            tg_id=user_id,
            details=ad_text[:100]
        )

        await message.answer(
            config.SUCCESS_MESSAGE.format(channel_id=config.CHANNEL_ID)
        )
        logger.info(
            f"Объявление ID_{message.message_id} от пользователя @{username} ({user_id}) "
            f"успешно опубликовано с хештегом {hashtag}"
        )

    except Exception as e:
        logger.error(f"Ошибка при публикации объявления от пользователя {user_id}: {e}")
        await message.answer(
            config.ERROR_MESSAGE.format(admin_username=config.ADMIN_USERNAME)
        )


# ====== ОТСЛЕЖИВАНИЕ ОТПИСОК ======

@router.chat_member()
async def track_channel_member_updates(update: ChatMemberUpdated, state: FSMContext):
    """Отслеживание изменений статуса подписки на канал"""

    # Проверяем, что это наш канал
    if update.chat.id != config.CHANNEL_CHAT_ID:
        return

    old_status = update.old_chat_member.status
    new_status = update.new_chat_member.status
    user_id = update.from_user.id

    # Проверка на отписку
    was_member = old_status in [
        ChatMemberStatus.MEMBER,
        ChatMemberStatus.ADMINISTRATOR,
        ChatMemberStatus.CREATOR
    ]
    is_not_member = new_status in [ChatMemberStatus.LEFT, ChatMemberStatus.KICKED]

    if was_member and is_not_member:
        try:
            user_data = await state.get_data()

            # Отправляем вопрос только один раз
            if not user_data.get('unsubscribe_question_asked'):
                await bot.send_message(
                    chat_id=user_id,
                    text=config.UNSUBSCRIBE_QUESTION.format(channel_id=config.CHANNEL_ID)
                )
                await state.update_data(unsubscribe_question_asked=True)
                logger.info(f"Пользователь {user_id} отписался от канала. Отправлен вопрос.")
        except Exception as e:
            logger.error(f"Ошибка при отправке вопроса об отписке пользователю {user_id}: {e}")


# ====== СОБЫТИЯ ЗАПУСКА/ОСТАНОВКИ ======

async def on_startup():
    """Действия при запуске бота"""
    logger.info("=" * 60)
    logger.info("🚀 Бот @DriverVakhtaBot запущен")
    logger.info("=" * 60)
    logger.info(f"📢 Канал: {config.CHANNEL_ID}")
    logger.info(f"🆔 ID канала: {config.CHANNEL_CHAT_ID}")
    logger.info(f"💬 Группа обсуждений: {config.DISCUSSION_GROUP}")
    logger.info(f"👤 Администратор: @{config.ADMIN_USERNAME}")
    logger.info(f"📧 Email администратора: {config.ADMIN_EMAIL}")
    logger.info(f"📝 Фраз для резюме: {len(config.RESUME_PHRASES)}")
    logger.info(f"📝 Фраз для вакансий: {len(config.VACANCY_PHRASES)}")
    logger.info(f"🚫 Запрещенных слов: {len(config.BANNED_WORDS)}")
    logger.info(f"👥 Админов панели: {len(ADMIN_IDS)}")
    logger.info("=" * 60)

    # Проверка конфигурации
    config.validate()

    # Статистика из БД
    users_stats = db.get_users_count()
    ads_stats = db.get_ads_stats()
    logger.info(f"📊 Пользователей в БД: {users_stats['total']}")
    logger.info(f"📊 Объявлений в БД: {ads_stats['total']}")


async def on_shutdown():
    """Действия при остановке бота"""
    logger.info("=" * 60)
    logger.info("🛑 Бот остановлен")
    logger.info("=" * 60)


# ====== ГЛАВНАЯ ФУНКЦИЯ ======

async def main():
    """Главная функция запуска бота"""

    # Регистрация роутеров
    dp.include_routers(admin_router, router)

    # События
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    try:
        # Запуск polling
        await dp.start_polling(
            bot,
            allowed_updates=["message", "chat_member", "callback_query"],
            drop_pending_updates=True
        )
    finally:
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("⌨️  Бот остановлен пользователем (Ctrl+C)")
    except Exception as e:

        logger.error(f"❌ Критическая ошибка: {e}")

