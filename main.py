"""
Telegram бот для канала @vakhtasever
Автоматическое размещение объявлений о работе
Версия 2.0 - С исправлениями по ТЗ
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, ChatMemberUpdated
from aiogram.enums import ChatMemberStatus, ChatType
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
        is_subscribed = member.status in [
            ChatMemberStatus.MEMBER,
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.CREATOR
        ]

        # Обновляем статус в БД
        db.update_user_subscription(user_id, is_subscribed)

        return is_subscribed
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


def check_contact_info(text: str) -> bool:
    """
    Проверка наличия контактной информации в объявлении
    Возвращает True если есть номер телефона или @username
    """
    import re

    # Проверка на номер телефона (различные форматы)
    phone_patterns = [
        r'\+?\d[\d\s\-\(\)]{9,}',  # +7 999 999-99-99, 8-999-999-99-99, и т.д.
        r'\d{10,}',  # 9999999999
    ]

    for pattern in phone_patterns:
        if re.search(pattern, text):
            return True

    # Проверка на @username или telegram
    if '@' in text or 'telegram' in text.lower() or 'тг' in text.lower():
        return True

    return False





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

    welcome_text = (
        "👋 Добро пожаловать в бот для размещения объявлений в канале "
        "«Водители, Машинисты, Работа, Вахта» (t.me/vakhtasever)!\n\n"
        "📝 <b>Здесь вы можете бесплатно разместить:</b>\n"
        "• резюме (если ищете работу водителем, машинистом и т. д.);\n"
        "• вакансию (если ищете сотрудников на эти специальности).\n\n"
        f"⚠️ <b>ВАЖНО:</b> Перед отправкой объявления обязательно подпишитесь на канал: {config.CHANNEL_ID}\n\n"
        "📋 <b>Доступные команды:</b>\n"
        "/rules - Правила размещения объявлений\n"
        "/help - Помощь по работе с ботом\n\n"
        f"💬 Чат водителей и машинистов: {config.DISCUSSION_GROUP}\n"
        f"👤 Админ канала: t.me/{config.ADMIN_USERNAME}"
    )

    await message.answer(welcome_text, parse_mode="HTML")
    logger.info(f"Пользователь {message.from_user.id} (@{message.from_user.username}) запустил бота")


@router.message(Command("help"))
async def cmd_help(message: Message):
    """Обработчик команды /help"""
    help_text = (
        "ℹ️ <b>Помощь по работе с ботом</b>\n\n"
        "<b>Как разместить объявление:</b>\n"
        "1. Подпишитесь на канал @vakhtasever\n"
        "2. Отправьте боту текст объявления\n"
        "3. Начните объявление с разрешённой фразы (см. /rules)\n"
        "4. Обязательно укажите контакты (телефон или @username)\n\n"
        "<b>Важно:</b>\n"
        "• Объявление должно быть только текстом (без фото/файлов)\n"
        "• Запрещена нецензурная лексика\n"
        "• Не забудьте указать контакты для связи!\n\n"
        "<b>Команды:</b>\n"
        "/start - Начать работу с ботом\n"
        "/rules - Правила размещения объявлений\n"
        "/help - Эта справка\n\n"
        f"Вопросы? Напишите админу: t.me/{config.ADMIN_USERNAME}"
    )

    await message.answer(help_text, parse_mode="HTML")


@router.message(Command("rules"))
async def cmd_rules(message: Message):
    """Обработчик команды /rules"""

    # Формируем список фраз для резюме
    resume_list = "\n".join([f"• «{phrase}»" for phrase in config.RESUME_PHRASES])

    # Формируем список фраз для вакансий
    vacancy_list = "\n".join([f"• «{phrase}»" for phrase in config.VACANCY_PHRASES])

    rules_text = f"""📋 <b>Правила размещения объявлений в канале {config.CHANNEL_ID}</b>

<b>1. Обязательное условие — подписка на канал</b>
Перед отправкой объявления вы должны быть подписаны на канал {config.CHANNEL_ID}. Бот автоматически проверяет подписку.

<b>2. Как отправить объявление</b>
Отправьте одно текстовое сообщение боту. Фото, файлы и ссылки прикреплять нельзя.

<b>3. Начало объявления</b>
Ваше сообщение обязательно должно начинаться с одной из следующих фраз:

<b>Для соискателей (резюме):</b>
{resume_list}

<b>Для работодателей (вакансии):</b>
{vacancy_list}

⚠️ <b>Важно:</b> фраза должна быть в начале сообщения, без лишних слов перед ней.

<b>4. Обязательная контактная информация</b>
⚠️ <b>ВАЖНО! Каждое объявление должно содержать:</b>
• Номер телефона для связи
• Или username в Telegram (@ваш_username)
• Без контактов объявление будет отклонено!

<b>5. Содержание объявления</b>

<b>Если вы соискатель (ищете работу):</b>
• ФИО
• специальность/разряд
• стаж работы
• ключевые навыки
• регион поиска работы
• <b>КОНТАКТЫ (телефон/Telegram)</b>

<b>Если вы работодатель (ищете сотрудника):</b>
• должность
• тип спецтехники
• регион работы
• условия работы (зарплата, график)
• <b>КОНТАКТЫ (телефон/Telegram)</b>

<b>6. Что запрещено</b>
• отправка фото, видео, документов
• спам, реклама, нецензурная лексика
• объявления без контактов
• объявления без стартовой фразы

<b>7. Помощь и поддержка</b>
Если у вас остались вопросы: t.me/{config.ADMIN_USERNAME}"""

    await message.answer(rules_text, parse_mode="HTML")
    logger.info(f"Пользователь {message.from_user.id} запросил правила")


# ====== ОБРАБОТЧИКИ МЕДИАФАЙЛОВ ======

@router.message(F.photo | F.video | F.document | F.audio | F.voice | F.sticker | F.video_note | F.animation)
async def handle_media(message: Message):
    """Обработчик медиафайлов - отклонение"""
    await message.answer(
        "❌ Объявление должно быть в текстовом формате.\n\n"
        "Отправьте текст заново без прикреплённых файлов, фото или видео."
    )
    logger.info(f"Пользователь {message.from_user.id} отправил медиафайл")


# ====== ОБРАБОТЧИК ТЕКСТОВЫХ СООБЩЕНИЙ ======

@router.message(F.text)
async def handle_text_message(message: Message, state: FSMContext):
    """Главный обработчик текстовых сообщений (объявлений)"""

    # Игнорируем неизвестные команды
    if message.text.startswith('/'):
        if message.text not in ['/start', '/rules', '/help']:
            await message.answer(
                "❓ Неизвестная команда.\n\n"
                "Используйте:\n"
                "/start - Начать работу\n"
                "/rules - Правила размещения\n"
                "/help - Помощь"
            )
        return

    # Проверка на пустое сообщение
    if not message.text or not message.text.strip():
        await message.answer("❌ Сообщение не может быть пустым. Отправьте объявление заново.")
        return

    user_id = message.from_user.id
    username = message.from_user.username
    ad_text = message.text.strip()

    logger.info(f"Получено объявление от пользователя {user_id} (@{username})")

    # ПРОВЕРКА 1: Подписка на канал (п.2 из документа)
    is_subscribed = await check_subscription(user_id)
    if not is_subscribed:
        await message.answer(
            f"⚠️ <b>Для размещения объявлений необходимо подписаться на канал:</b> {config.CHANNEL_ID}\n\n"
            f"После подписки отправьте ваше объявление снова.",
            parse_mode="HTML"
        )
        logger.info(f"Пользователь {user_id} не подписан на канал")

        # Логируем
        db.add_log(
            log_type="no_subscription",
            message=f"Попытка отправить объявление без подписки от @{username}",
            tg_id=user_id
        )
        return

    # ПРОВЕРКА 2: Запрещенные слова
    if check_banned_words(ad_text):
        rejection_reason = "Использование запрещенных слов (нецензурная лексика)"

        # Сохраняем отклоненное объявление
        ad_id = db.add_ad(
            tg_id=user_id,
            username=username,
            ad_text=ad_text,
            ad_type="unknown",
            status="rejected",
            rejection_reason=rejection_reason
        )

        # Логируем отклонение (п.3 из документа)
        db.add_log(
            log_type="ad_rejected",
            message=f"Объявление ID_{ad_id} отклонено: {rejection_reason}",
            tg_id=user_id,
            details=ad_text[:100]
        )

        # Отправляем пользователю сообщение об отклонении (п.3 из документа)
        await message.answer(
            f"❌ <b>Ваше объявление не соответствует правилам размещения.</b>\n\n"
            f"Причина: {rejection_reason}\n\n"
            f"Отправьте /rules, чтобы ознакомиться с правилами, исправьте объявление и отправьте снова.\n\n"
            f"Если у вас возникли вопросы, напишите админу канала: t.me/{config.ADMIN_USERNAME}",
            parse_mode="HTML"
        )

        # Отправляем email (п.3 из документа)

    # ПРОВЕРКА 3: Начальная фраза (п.3 из документа)
    ad_type = validate_ad_start(ad_text)
    if not ad_type:
        rejection_reason = "Объявление не начинается с разрешенной фразы"

        # Сохраняем отклоненное объявление
        ad_id = db.add_ad(
            tg_id=user_id,
            username=username,
            ad_text=ad_text,
            ad_type="unknown",
            status="rejected",
            rejection_reason=rejection_reason
        )

        # Логируем отклонение (п.3 из документа)
        db.add_log(
            log_type="ad_rejected",
            message=f"Объявление ID_{ad_id} отклонено: {rejection_reason}",
            tg_id=user_id,
            details=ad_text[:100]
        )

        # Отправляем пользователю сообщение об отклонении (п.3 из документа)
        await message.answer(
            f"❌ <b>Ваше объявление не соответствует правилам размещения.</b>\n\n"
            f"Причина: {rejection_reason}\n\n"
            f"Объявление должно начинаться с одной из разрешённых фраз.\n"
            f"Отправьте /rules, чтобы узнать правильный формат.\n\n"
            f"Если у вас возникли вопросы, напишите админу канала: t.me/{config.ADMIN_USERNAME}",
            parse_mode="HTML"
        )

        # Отправляем email (п.3 из документа)


    # ПРОВЕРКА 4: Наличие контактной информации (п.9 из документа)
    if not check_contact_info(ad_text):
        rejection_reason = "Отсутствует контактная информация (номер телефона или @username)"

        # Сохраняем отклоненное объявление
        ad_id = db.add_ad(
            tg_id=user_id,
            username=username,
            ad_text=ad_text,
            ad_type=ad_type,
            status="rejected",
            rejection_reason=rejection_reason
        )

        # Логируем отклонение
        db.add_log(
            log_type="ad_rejected",
            message=f"Объявление ID_{ad_id} отклонено: {rejection_reason}",
            tg_id=user_id,
            details=ad_text[:100]
        )

        # Отправляем пользователю сообщение об отклонении
        await message.answer(
            f"❌ <b>Ваше объявление не соответствует правилам размещения.</b>\n\n"
            f"Причина: {rejection_reason}\n\n"
            f"⚠️ Обязательно укажите в объявлении:\n"
            f"• Номер телефона для связи\n"
            f"• Или ваш username в Telegram (@username)\n\n"
            f"Исправьте объявление и отправьте снова.\n\n"
            f"Если у вас возникли вопросы, напишите админу канала: t.me/{config.ADMIN_USERNAME}",
            parse_mode="HTML"
        )

        # Отправляем email

    # ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ - ПУБЛИКУЕМ

    # Определение хештега
    hashtag = config.RESUME_HASHTAG if ad_type == "resume" else config.VACANCY_HASHTAG

    try:
        # Публикуем в канале
        post_text = f"{ad_text}\n\n{hashtag}"
        sent_message = await bot.send_message(
            chat_id=config.CHANNEL_CHAT_ID,
            text=post_text
        )

        # Сохраняем объявление в БД
        ad_id = db.add_ad(
            tg_id=user_id,
            username=username,
            ad_text=ad_text,
            ad_type=ad_type,
            status="published",
            message_id=sent_message.message_id
        )

        # Логируем успех (п.4 из документа)
        db.add_log(
            log_type="ad_published",
            message=f"Объявление ID_{ad_id} от пользователя @{username} успешно опубликовано",
            tg_id=user_id,
            details=ad_text[:100]
        )

        # Отправляем подтверждение пользователю (п.4 из документа)
        await message.answer(
            f"✅ <b>Ваше объявление размещено в канале:</b> {config.CHANNEL_ID}\n\n"
            f"Спасибо за использование нашего сервиса!",
            parse_mode="HTML"
        )

        logger.info(
            f"Объявление ID_{ad_id} от пользователя @{username} ({user_id}) "
            f"успешно опубликовано с хештегом {hashtag}"
        )

    except Exception as e:
        logger.error(f"Ошибка при публикации объявления от пользователя {user_id}: {e}")
        await message.answer(
            f"❌ Произошла ошибка при публикации объявления.\n\n"
            f"Пожалуйста, попробуйте позже или свяжитесь с администратором: t.me/{config.ADMIN_USERNAME}"
        )


# ====== ОТСЛЕЖИВАНИЕ ПОДПИСОК/ОТПИСОК ======

@router.chat_member()
async def track_channel_member_updates(update: ChatMemberUpdated):
    """Отслеживание изменений статуса подписки на канал"""

    # Проверяем, что это наш канал
    if update.chat.id != config.CHANNEL_CHAT_ID:
        return

    old_status = update.old_chat_member.status
    new_status = update.new_chat_member.status
    user_id = update.from_user.id

    # Проверка на НОВУЮ ПОДПИСКУ (п.7 из документа)
    was_not_member = old_status in [ChatMemberStatus.LEFT, ChatMemberStatus.KICKED]
    is_now_member = new_status in [
        ChatMemberStatus.MEMBER,
        ChatMemberStatus.ADMINISTRATOR,
        ChatMemberStatus.CREATOR
    ]

    if was_not_member and is_now_member:
        # Отправляем приветствие новому подписчику (п.7 из документа)
        try:
            welcome_message = (
                f"👋 Добро пожаловать в канал «Водители, Машинисты, Работа, Вахта»!\n\n"
                f"📝 <b>Как разместить объявление:</b>\n"
                f"1. Перейдите в бот: t.me/DriverVakhtaBot\n"
                f"2. Отправьте /start\n"
                f"3. Отправьте текст объявления\n\n"
                f"📋 Правила размещения: отправьте боту команду /rules\n\n"
                f"💬 Присоединяйтесь к обсуждениям: {config.DISCUSSION_GROUP}\n"
                f"👤 Админ: t.me/{config.ADMIN_USERNAME}"
            )

            await bot.send_message(
                chat_id=user_id,
                text=welcome_message,
                parse_mode="HTML"
            )

            # Обновляем статус подписки в БД
            db.update_user_subscription(user_id, True)

            logger.info(f"Пользователь {user_id} подписался на канал. Отправлено приветствие.")
        except Exception as e:
            logger.error(f"Ошибка при отправке приветствия пользователю {user_id}: {e}")

    # Проверка на ОТПИСКУ (п.1 из документа)
    was_member = old_status in [
        ChatMemberStatus.MEMBER,
        ChatMemberStatus.ADMINISTRATOR,
        ChatMemberStatus.CREATOR
    ]
    is_not_member = new_status in [ChatMemberStatus.LEFT, ChatMemberStatus.KICKED]

    if was_member and is_not_member:
        try:
            # Отправляем вопрос КАЖДЫЙ РАЗ при отписке
            await bot.send_message(
                chat_id=user_id,
                text=f"Что вам не понравилось в канале {config.CHANNEL_ID}?"
            )

            # Обновляем статус подписки в БД
            db.update_user_subscription(user_id, False)

            # Логируем
            db.add_log(
                log_type="unsubscribe",
                message=f"Пользователь {user_id} отписался от канала",
                tg_id=user_id
            )

            logger.info(f"Пользователь {user_id} отписался от канала. Отправлен вопрос.")
        except Exception as e:
            logger.error(f"Ошибка при отправке вопроса об отписке пользователю {user_id}: {e}")


# ====== СОБЫТИЯ ЗАПУСКА/ОСТАНОВКИ ======

async def on_startup():
    """Действия при запуске бота"""
    logger.info("=" * 60)
    logger.info("🚀 Бот @DriverVakhtaBot запущен (v2.0)")
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
    dp.include_router(admin_router)  # Админ-панель
    dp.include_router(router)  # Основной роутер

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


