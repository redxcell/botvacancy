"""
Telegram бот для канала @vakhtasever
Автоматическое размещение объявлений о работе
Версия 3.0 - Запрос номера телефона перед объявлением
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional
import re

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, ChatMemberUpdated, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
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
class AdCreationStates(StatesGroup):
    waiting_for_phone = State()
    waiting_for_ad_text = State()

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


def validate_phone_number(text: str) -> Optional[str]:
    """
    Валидация и нормализация номера телефона
    Возвращает отформатированный номер или None
    """
    # Убираем все кроме цифр и +
    cleaned = re.sub(r'[^\d+]', '', text)
    
    # Проверяем различные форматы
    patterns = [
        r'^\+7\d{10}$',      # +79991234567
        r'^8\d{10}$',        # 89991234567
        r'^7\d{10}$',        # 79991234567
        r'^\d{10}$',         # 9991234567
        r'^\+\d{11,15}$',    # Международный формат
    ]
    
    for pattern in patterns:
        if re.match(pattern, cleaned):
            # Нормализуем к формату +7...
            if cleaned.startswith('8'):
                return '+7' + cleaned[1:]
            elif cleaned.startswith('7') and not cleaned.startswith('+'):
                return '+' + cleaned
            elif cleaned.startswith('9'):
                return '+7' + cleaned
            else:
                return cleaned
    
    return None


def get_phone_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура с кнопкой отправки номера телефона"""
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📱 Отправить номер телефона", request_contact=True)]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    return keyboard


# ====== ОБРАБОТЧИКИ КОМАНД ======

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    """Обработчик команды /start - сразу начинаем подачу объявления"""
    # Очищаем предыдущее состояние
    await state.clear()
    
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
    
    # Проверка подписки
    is_subscribed = await check_subscription(message.from_user.id)
    if not is_subscribed:
        await message.answer(
            f"⚠️ <b>Для размещения объявлений необходимо подписаться на канал:</b> {config.CHANNEL_ID}\n\n"
            f"После подписки отправьте /start снова.",
            parse_mode="HTML",
            reply_markup=ReplyKeyboardRemove()
        )
        return
    
    welcome_text = (
        "👋 <b>Здравствуйте!</b>\n\n"
        "📋 <b>РЕЗЮМЕ</b> принимаем только от:\n"
        "• водителей\n"
        "• машинистов спецтехники\n"
        "• автослесарей\n"
        "• автомехаников\n\n"
        "📌 Начните сообщение с фразы:\n"
        "«Ищу работу водителем…» / «машинистом…» / «автослесарем» / «автомехаником»\n\n"
        "Далее кратко напишите о себе:\n"
        "ФИО → профессия/разряд → стаж → навыки → город проживания → регион поиска работы\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "💼 <b>ВАКАНСИИ</b> принимаем только для:\n"
        "• водителей\n"
        "• машинистов спецтехники\n"
        "• автомехаников\n"
        "• автослесарей\n\n"
        "📌 Начните объявление с фразы:\n"
        "«Требуются водители…» / «машинисты…» / «автомеханики» / «автослесаря»\n\n"
        "Далее кратко опишите:\n"
        "должность → тип спецтехники → регион/город → условия (зарплата, график и т. д.)\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"❗ Подписка на {config.CHANNEL_ID} обязательна.\n"
        "❌ Фото/файлы/видео/ссылки — запрещены.\n\n"
        f"🔔 Ваше объявление опубликуют после модерации в канале {config.CHANNEL_ID}\n\n"
        "<b>Доступные команды:</b>\n"
        "/rules - Подробные правила\n"
        "/help - Помощь\n\n"
        f"💬 Чат: {config.DISCUSSION_GROUP}\n"
        f"👤 Админ: t.me/{config.ADMIN_USERNAME}"
    )
    
    await message.answer(welcome_text, parse_mode="HTML", reply_markup=ReplyKeyboardRemove())
    logger.info(f"Пользователь {message.from_user.id} (@{message.from_user.username}) запустил бота")
    
    # Сразу запускаем процесс подачи объявления
    await state.set_state(AdCreationStates.waiting_for_phone)
    
    await message.answer(
        "📞 <b>Шаг 1 из 2: Контактный номер телефона</b>\n\n"
        "Укажите ваш номер телефона для связи.\n\n"
        "Вы можете:\n"
        "• Нажать кнопку \"📱 Отправить номер\" ниже\n"
        "• Или написать номер вручную (например: +79991234567)\n\n"
        "Для отмены отправьте /cancel",
        parse_mode="HTML",
        reply_markup=get_phone_keyboard()
    )


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    """Отмена создания объявления"""
    current_state = await state.get_state()
    if current_state is None:
        await message.answer("Нечего отменять.", reply_markup=ReplyKeyboardRemove())
        return
    
    await state.clear()
    await message.answer(
        "❌ Создание объявления отменено.\n\n"
        "Чтобы начать заново, отправьте /start",
        reply_markup=ReplyKeyboardRemove()
    )


@router.message(Command("help"))
async def cmd_help(message: Message):
    """Обработчик команды /help"""
    help_text = (
        "ℹ️ <b>Помощь по работе с ботом</b>\n\n"
        "<b>Как разместить объявление:</b>\n"
        "1. Отправьте /start\n"
        "2. Укажите номер телефона\n"
        "3. Отправьте текст объявления\n"
        "4. Объявление начните с разрешённой фразы (см. /rules)\n\n"
        "<b>Важно:</b>\n"
        "• Подпишитесь на канал @vakhtasever\n"
        "• Объявление должно быть только текстом (без фото/файлов)\n"
        "• Запрещена нецензурная лексика\n\n"
        "<b>Команды:</b>\n"
        "/start - Подать объявление\n"
        "/rules - Правила размещения\n"
        "/help - Эта справка\n"
        "/cancel - Отменить создание объявления\n\n"
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
• Отправьте команду /new
• Укажите номер телефона
• Отправьте текст объявления (только текст, без фото/файлов)

<b>3. Начало объявления</b>
Ваше сообщение обязательно должно начинаться с одной из следующих фраз:

<b>Для соискателей (резюме):</b>
{resume_list}

<b>Для работодателей (вакансии):</b>
{vacancy_list}

⚠️ <b>Важно:</b> фраза должна быть в начале сообщения, без лишних слов перед ней.

<b>4. Содержание объявления</b>

<b>Если вы соискатель (ищете работу):</b>
• ФИО
• специальность/разряд
• стаж работы
• ключевые навыки
• регион поиска работы

<b>Если вы работодатель (ищете сотрудника):</b>
• должность
• тип спецтехники
• регион работы
• условия работы (зарплата, график)

<b>5. Что запрещено</b>
• отправка фото, видео, документов
• спам, реклама, нецензурная лексика
• объявления без стартовой фразы

<b>6. Помощь и поддержка</b>
Если у вас остались вопросы: t.me/{config.ADMIN_USERNAME}"""
    
    await message.answer(rules_text, parse_mode="HTML")
    logger.info(f"Пользователь {message.from_user.id} запросил правила")


# ====== ОБРАБОТЧИК НОМЕРА ТЕЛЕФОНА ======

@router.message(AdCreationStates.waiting_for_phone, F.contact)
async def process_contact(message: Message, state: FSMContext):
    """Обработка контакта через кнопку"""
    phone = message.contact.phone_number
    
    # Нормализуем номер
    if not phone.startswith('+'):
        phone = '+' + phone
    
    # Сохраняем номер в состояние
    await state.update_data(phone=phone)
    await state.set_state(AdCreationStates.waiting_for_ad_text)
    
    await message.answer(
        f"✅ Номер телефона сохранен: {phone}\n\n"
        "📝 <b>Шаг 2 из 2: Текст объявления</b>\n\n"
        "Теперь отправьте текст вашего объявления.\n\n"
        "⚠️ <b>Важно:</b>\n"
        "• Начните с разрешённой фразы (см. /rules)\n"
        "• Только текст, без фото и файлов\n"
        "• Без нецензурной лексики\n\n"
        "Для отмены отправьте /cancel",
        parse_mode="HTML",
        reply_markup=ReplyKeyboardRemove()
    )


@router.message(AdCreationStates.waiting_for_phone, F.text)
async def process_phone_text(message: Message, state: FSMContext):
    """Обработка номера телефона в текстовом виде"""
    # Проверяем на команды
    if message.text.startswith('/'):
        return
    
    phone = validate_phone_number(message.text)
    
    if not phone:
        await message.answer(
            "❌ Неверный формат номера телефона.\n\n"
            "Примеры правильных форматов:\n"
            "• +79991234567\n"
            "• 89991234567\n"
            "• 79991234567\n\n"
            "Попробуйте ещё раз или нажмите кнопку \"📱 Отправить номер\"",
            reply_markup=get_phone_keyboard()
        )
        return
    
    # Сохраняем номер в состояние
    await state.update_data(phone=phone)
    await state.set_state(AdCreationStates.waiting_for_ad_text)
    
    await message.answer(
        f"✅ Номер телефона сохранен: {phone}\n\n"
        "📝 <b>Шаг 2 из 2: Текст объявления</b>\n\n"
        "Теперь отправьте текст вашего объявления.\n\n"
        "⚠️ <b>Важно:</b>\n"
        "• Начните с разрешённой фразы (см. /rules)\n"
        "• Только текст, без фото и файлов\n"
        "• Без нецензурной лексики\n\n"
        "Для отмены отправьте /cancel",
        parse_mode="HTML",
        reply_markup=ReplyKeyboardRemove()
    )


# ====== ОБРАБОТЧИК МЕДИАФАЙЛОВ В СОСТОЯНИИ ОЖИДАНИЯ ОБЪЯВЛЕНИЯ ======

@router.message(AdCreationStates.waiting_for_ad_text, F.photo | F.video | F.document | F.audio | F.voice | F.sticker)
async def handle_media_in_ad(message: Message):
    """Обработчик медиафайлов при создании объявления"""
    await message.answer(
        "❌ Объявление должно быть только текстом.\n\n"
        "Отправьте текст объявления без прикреплённых файлов, фото или видео.\n\n"
        "Для отмены отправьте /cancel"
    )


# ====== ОБРАБОТЧИК ТЕКСТА ОБЪЯВЛЕНИЯ ======

@router.message(AdCreationStates.waiting_for_ad_text, F.text)
async def process_ad_text(message: Message, state: FSMContext):
    """Обработка текста объявления"""
    
    # Проверяем на команды
    if message.text.startswith('/'):
        return
    
    # Получаем данные из состояния
    data = await state.get_data()
    phone = data.get('phone')
    
    if not phone:
        await message.answer("❌ Ошибка: номер телефона не найден. Начните заново с /new")
        await state.clear()
        return
    
    user_id = message.from_user.id
    username = message.from_user.username
    ad_text = message.text.strip()
    
    logger.info(f"Получено объявление от пользователя {user_id} (@{username})")
    
    # ПРОВЕРКА 1: Запрещенные слова
    if check_banned_words(ad_text):
        rejection_reason = "Использование запрещенных слов (нецензурная лексика)"
        
        ad_id = db.add_ad(
            tg_id=user_id,
            username=username,
            ad_text=f"{ad_text}\n\n📞 Контакт: {phone}",
            ad_type="unknown",
            status="rejected",
            rejection_reason=rejection_reason
        )
        
        db.add_log(
            log_type="ad_rejected",
            message=f"Объявление ID_{ad_id} отклонено: {rejection_reason}",
            tg_id=user_id,
            details=ad_text[:100]
        )
        
        await message.answer(
            f"❌ <b>Ваше объявление не соответствует правилам размещения.</b>\n\n"
            f"Причина: {rejection_reason}\n\n"
            f"Отправьте /rules, чтобы ознакомиться с правилами.\n"
            f"Для создания нового объявления отправьте /start\n\n"
            f"Если у вас возникли вопросы, напишите админу канала: t.me/{config.ADMIN_USERNAME}",
            parse_mode="HTML",
            reply_markup=ReplyKeyboardRemove()
        )
        
        await state.clear()
        logger.warning(f"Объявление ID_{ad_id} отклонено: {rejection_reason}")
        return
    
    # ПРОВЕРКА 2: Начальная фраза
    ad_type = validate_ad_start(ad_text)
    if not ad_type:
        rejection_reason = "Объявление не начинается с разрешенной фразы"
        
        ad_id = db.add_ad(
            tg_id=user_id,
            username=username,
            ad_text=f"{ad_text}\n\n📞 Контакт: {phone}",
            ad_type="unknown",
            status="rejected",
            rejection_reason=rejection_reason
        )
        
        db.add_log(
            log_type="ad_rejected",
            message=f"Объявление ID_{ad_id} отклонено: {rejection_reason}",
            tg_id=user_id,
            details=ad_text[:100]
        )
        
        await message.answer(
            f"❌ <b>Ваше объявление не соответствует правилам размещения.</b>\n\n"
            f"Причина: {rejection_reason}\n\n"
            f"Объявление должно начинаться с одной из разрешённых фраз.\n"
            f"Отправьте /rules, чтобы узнать правильный формат.\n"
            f"Для создания нового объявления отправьте /start\n\n"
            f"Если у вас возникли вопросы, напишите админу канала: t.me/{config.ADMIN_USERNAME}",
            parse_mode="HTML",
            reply_markup=ReplyKeyboardRemove()
        )
        
        await state.clear()
        logger.warning(f"Объявление ID_{ad_id} отклонено: {rejection_reason}")
        return
    
    # ====== ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ - ПУБЛИКУЕМ ======
    
    hashtag = config.RESUME_HASHTAG if ad_type == "resume" else config.VACANCY_HASHTAG
    
    # Формируем финальный текст с номером телефона
    final_text = f"{ad_text}\n\n📞 Контакт: {phone}"
    
    try:
        # Публикуем в канале
        post_text = f"{final_text}\n\n{hashtag}"
        sent_message = await bot.send_message(
            chat_id=config.CHANNEL_CHAT_ID,
            text=post_text
        )
        
        # Сохраняем объявление в БД
        ad_id = db.add_ad(
            tg_id=user_id,
            username=username,
            ad_text=final_text,
            ad_type=ad_type,
            status="published",
            message_id=sent_message.message_id
        )
        
        # Логируем успех
        db.add_log(
            log_type="ad_published",
            message=f"Объявление ID_{ad_id} от пользователя @{username} успешно опубликовано",
            tg_id=user_id,
            details=ad_text[:100]
        )
        
        # Отправляем подтверждение пользователю
        await message.answer(
            f"✅ <b>Ваше объявление размещено в канале:</b> {config.CHANNEL_ID}\n\n"
            f"Спасибо за использование нашего сервиса!\n\n"
            f"Чтобы разместить ещё одно объявление, отправьте /start",
            parse_mode="HTML",
            reply_markup=ReplyKeyboardRemove()
        )
        
        # Очищаем состояние
        await state.clear()
        
        logger.info(
            f"Объявление ID_{ad_id} от пользователя @{username} ({user_id}) "
            f"успешно опубликовано с хештегом {hashtag}"
        )
        
    except Exception as e:
        logger.error(f"Ошибка при публикации объявления от пользователя {user_id}: {e}")
        await message.answer(
            f"❌ Произошла ошибка при публикации объявления.\n\n"
            f"Пожалуйста, попробуйте позже или свяжитесь с администратором: t.me/{config.ADMIN_USERNAME}",
            reply_markup=ReplyKeyboardRemove()
        )
        await state.clear()


# ====== ОБРАБОТЧИК МЕДИАФАЙЛОВ ВНЕ СОСТОЯНИЯ ======

@router.message(F.photo | F.video | F.document | F.audio | F.voice | F.sticker | F.video_note | F.animation)
async def handle_media(message: Message):
    """Обработчик медиафайлов вне процесса создания объявления"""
    await message.answer(
        "❓ Для размещения объявления отправьте /start\n\n"
        "Объявление должно быть только текстом, без файлов и фото."
    )


# ====== ОБРАБОТЧИК ТЕКСТА ВНЕ СОСТОЯНИЯ ======

@router.message(F.text)
async def handle_text_outside_state(message: Message):
    """Обработчик текста вне процесса создания объявления"""
    
    # Игнорируем команды
    if message.text.startswith('/'):
        await message.answer(
            "❓ Неизвестная команда.\n\n"
            "Доступные команды:\n"
            "/start - Подать объявление\n"
            "/rules - Правила размещения\n"
            "/help - Помощь"
        )
        return
    
    # Если пользователь пишет просто текст
    await message.answer(
        "📝 Для размещения объявления отправьте /start\n\n"
        "Затем следуйте инструкциям бота:\n"
        "1. Укажите номер телефона\n"
        "2. Отправьте текст объявления\n\n"
        "Для просмотра правил отправьте /rules"
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
    
    # Проверка на НОВУЮ ПОДПИСКУ
    was_not_member = old_status in [ChatMemberStatus.LEFT, ChatMemberStatus.KICKED]
    is_now_member = new_status in [
        ChatMemberStatus.MEMBER,
        ChatMemberStatus.ADMINISTRATOR,
        ChatMemberStatus.CREATOR
    ]
    
    if was_not_member and is_now_member:
        try:
            welcome_message = (
                f"👋 Добро пожаловать в канал «Водители, Машинисты, Работа, Вахта»!\n\n"
                f"📝 <b>Как разместить объявление:</b>\n"
                f"1. Перейдите в бот: t.me/DriverVakhtaBot\n"
                f"2. Отправьте /start\n"
                f"3. Укажите номер телефона\n"
                f"4. Отправьте текст объявления\n\n"
                f"📋 Правила: отправьте боту /rules\n\n"
                f"💬 Чат для обсуждений: {config.DISCUSSION_GROUP}\n"
                f"👤 Админ: t.me/{config.ADMIN_USERNAME}"
            )
            
            await bot.send_message(
                chat_id=user_id,
                text=welcome_message,
                parse_mode="HTML"
            )
            
            db.update_user_subscription(user_id, True)
            logger.info(f"Пользователь {user_id} подписался на канал. Отправлено приветствие.")
        except Exception as e:
            logger.error(f"Ошибка при отправке приветствия пользователю {user_id}: {e}")
    
    # Проверка на ОТПИСКУ
    was_member = old_status in [
        ChatMemberStatus.MEMBER,
        ChatMemberStatus.ADMINISTRATOR,
        ChatMemberStatus.CREATOR
    ]
    is_not_member = new_status in [ChatMemberStatus.LEFT, ChatMemberStatus.KICKED]
    
    if was_member and is_not_member:
        try:
            await bot.send_message(
                chat_id=user_id,
                text=f"Что вам не понравилось в канале {config.CHANNEL_ID}?"
            )
            
            db.update_user_subscription(user_id, False)
            
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
    logger.info("🚀 Бот @DriverVakhtaBot запущен (v3.0)")
    logger.info("=" * 60)
    logger.info(f"📢 Канал: {config.CHANNEL_ID}")
    logger.info(f"🆔 ID канала: {config.CHANNEL_CHAT_ID}")
    logger.info(f"💬 Группа обсуждений: {config.DISCUSSION_GROUP}")
    logger.info(f"👤 Администратор: @{config.ADMIN_USERNAME}")
    logger.info(f"📝 Фраз для резюме: {len(config.RESUME_PHRASES)}")
    logger.info(f"📝 Фраз для вакансий: {len(config.VACANCY_PHRASES)}")
    logger.info(f"🚫 Запрещенных слов: {len(config.BANNED_WORDS)}")
    logger.info(f"👥 Админов панели: {len(ADMIN_IDS)}")
    logger.info("=" * 60)
    
    config.validate()
    
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
    
    dp.include_router(admin_router)
    dp.include_router(router)
    
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    
    try:
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
