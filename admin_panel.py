"""
Админ-панель для бота
Функции: рассылка, статистика, логи, управление пользователями
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database import db
from config import config

logger = logging.getLogger(__name__)

# Роутер для админ-панели
admin_router = Router()

# Список админов (укажите Telegram ID администраторов)
ADMIN_IDS = [2066791910, 1665811858]


# ====== FSM СОСТОЯНИЯ ======

class BroadcastStates(StatesGroup):
    """Состояния для рассылки"""
    waiting_message = State()
    confirm_broadcast = State()


# ====== ПРОВЕРКА ПРАВ АДМИНА ======

def is_admin(user_id: int) -> bool:
    """Проверка, является ли пользователь администратором"""
    return user_id in ADMIN_IDS


# ====== КЛАВИАТУРЫ ======

def get_admin_menu_keyboard() -> InlineKeyboardMarkup:
    """Главное меню админ-панели"""
    keyboard = [
        [
            InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats"),
            InlineKeyboardButton(text="👥 Пользователи", callback_data="admin_users")
        ],
        [
            InlineKeyboardButton(text="📝 Объявления", callback_data="admin_ads"),
            InlineKeyboardButton(text="📋 Логи", callback_data="admin_logs")
        ],
        [
            InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast"),
            InlineKeyboardButton(text="📜 История рассылок", callback_data="admin_broadcast_history")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_logs_keyboard() -> InlineKeyboardMarkup:
    """Меню для просмотра логов"""
    keyboard = [
        [
            InlineKeyboardButton(text="🆕 Последние 50", callback_data="logs_latest_50"),
            InlineKeyboardButton(text="📝 Последние 100", callback_data="logs_latest_100")
        ],
        [
            InlineKeyboardButton(text="✅ Только опубликованные", callback_data="logs_published"),
            InlineKeyboardButton(text="❌ Только отклоненные", callback_data="logs_rejected")
        ],
        [
            InlineKeyboardButton(text="🔙 Назад", callback_data="admin_menu")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_ads_keyboard() -> InlineKeyboardMarkup:
    """Меню для просмотра объявлений"""
    keyboard = [
        [
            InlineKeyboardButton(text="📄 Последние 20", callback_data="ads_latest"),
            InlineKeyboardButton(text="✅ Опубликованные", callback_data="ads_published")
        ],
        [
            InlineKeyboardButton(text="❌ Отклоненные", callback_data="ads_rejected"),
            InlineKeyboardButton(text="💼 Вакансии", callback_data="ads_vacancies")
        ],
        [
            InlineKeyboardButton(text="📋 Резюме", callback_data="ads_resumes"),
            InlineKeyboardButton(text="🔙 Назад", callback_data="admin_menu")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_broadcast_confirm_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура подтверждения рассылки"""
    keyboard = [
        [
            InlineKeyboardButton(text="✅ Отправить", callback_data="broadcast_confirm"),
            InlineKeyboardButton(text="❌ Отменить", callback_data="broadcast_cancel")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_back_to_menu_keyboard() -> InlineKeyboardMarkup:
    """Кнопка возврата в меню"""
    keyboard = [[InlineKeyboardButton(text="🔙 Назад в меню", callback_data="admin_menu")]]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


# ====== КОМАНДЫ АДМИН-ПАНЕЛИ ======

@admin_router.message(Command("admin"))
async def cmd_admin(message: Message):
    """Команда для открытия админ-панели"""
    if not is_admin(message.from_user.id):
        await message.answer("❌ У вас нет доступа к админ-панели")
        return

    text = (
        "🔧 <b>Админ-панель бота @DriverVakhtaBot</b>\n\n"
        "Выберите действие:"
    )

    await message.answer(text, reply_markup=get_admin_menu_keyboard(), parse_mode="HTML")
    logger.info(f"Админ {message.from_user.id} открыл админ-панель")


@admin_router.callback_query(F.data == "admin_menu")
async def show_admin_menu(callback: CallbackQuery):
    """Показать главное меню админ-панели"""
    logger.info(f"Callback admin_menu от пользователя {callback.from_user.id}")

    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        logger.warning(f"Пользователь {callback.from_user.id} не является админом")
        return

    text = (
        "🔧 <b>Админ-панель бота @DriverVakhtaBot</b>\n\n"
        "Выберите действие:"
    )

    await callback.message.edit_text(text, reply_markup=get_admin_menu_keyboard(), parse_mode="HTML")
    await callback.answer()


# ====== СТАТИСТИКА ======

@admin_router.callback_query(F.data == "admin_stats")
async def show_stats(callback: CallbackQuery):
    """Показать статистику"""
    logger.info(f"Callback admin_stats от пользователя {callback.from_user.id}")

    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return

    try:
        # Получаем статистику
        users_stats = db.get_users_count()
        ads_stats = db.get_ads_stats()

        text = (
            "📊 <b>Статистика бота</b>\n\n"
            "<b>👥 Пользователи:</b>\n"
            f"├ Всего: {users_stats['total']}\n"
            f"├ Подписаны: {users_stats['subscribed']}\n"
            f"├ Активные: {users_stats['active']}\n"
            f"└ Заблокированы: {users_stats['blocked']}\n\n"
            "<b>📝 Объявления:</b>\n"
            f"├ Всего: {ads_stats['total']}\n"
            f"├ Опубликовано: {ads_stats['published']}\n"
            f"├ Отклонено: {ads_stats['rejected']}\n"
            f"├ Резюме: {ads_stats['resumes']}\n"
            f"└ Вакансии: {ads_stats['vacancies']}\n"
        )

        await callback.message.edit_text(text, reply_markup=get_back_to_menu_keyboard(), parse_mode="HTML")
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка в show_stats: {e}")
        await callback.answer("❌ Ошибка при получении статистики", show_alert=True)


# ====== ПОЛЬЗОВАТЕЛИ ======

@admin_router.callback_query(F.data == "admin_users")
async def show_users(callback: CallbackQuery):
    """Показать список пользователей"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return

    users = db.get_all_users(only_active=True)
    users_count = len(users)

    # Показываем последних 10 пользователей
    text = f"👥 <b>Последние пользователи ({users_count} всего)</b>\n\n"

    for i, user in enumerate(users[:10], 1):
        username = f"@{user['username']}" if user['username'] else "без username"
        subscribed = "✅" if user['is_subscribed'] else "❌"
        text += f"{i}. {username} (ID: {user['tg_id']}) {subscribed}\n"

    if users_count > 10:
        text += f"\n...и ещё {users_count - 10} пользователей"

    await callback.message.edit_text(text, reply_markup=get_back_to_menu_keyboard(), parse_mode="HTML")
    await callback.answer()


# ====== ОБЪЯВЛЕНИЯ ======

@admin_router.callback_query(F.data == "admin_ads")
async def show_ads_menu(callback: CallbackQuery):
    """Показать меню объявлений"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return

    text = "📝 <b>Объявления</b>\n\nВыберите категорию:"
    await callback.message.edit_text(text, reply_markup=get_ads_keyboard(), parse_mode="HTML")
    await callback.answer()


@admin_router.callback_query(F.data.startswith("ads_"))
async def show_ads_list(callback: CallbackQuery):
    """Показать список объявлений"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return

    action = callback.data.split("_")[1]

    # Определяем фильтры
    status = None
    ad_type = None
    limit = 20

    if action == "published":
        status = "published"
        title = "✅ Опубликованные объявления"
    elif action == "rejected":
        status = "rejected"
        title = "❌ Отклоненные объявления"
    elif action == "vacancies":
        ad_type = "vacancy"
        title = "💼 Вакансии"
    elif action == "resumes":
        ad_type = "resume"
        title = "📋 Резюме"
    else:
        title = "📄 Последние объявления"

    # Получаем объявления
    ads = db.get_ads(limit=limit, status=status, ad_type=ad_type)

    if not ads:
        text = f"{title}\n\nОбъявлений не найдено"
    else:
        text = f"<b>{title}</b>\n\n"

        for i, ad in enumerate(ads[:10], 1):
            username = f"@{ad['username']}" if ad['username'] else "без username"
            status_emoji = "✅" if ad['status'] == "published" else "❌"
            type_emoji = "📋" if ad['ad_type'] == "resume" else "💼"

            ad_preview = ad['ad_text'][:50] + "..." if len(ad['ad_text']) > 50 else ad['ad_text']

            text += f"{i}. {status_emoji} {type_emoji} {username}\n"
            text += f"   {ad_preview}\n"
            text += f"   {ad['created_at']}\n\n"

        if len(ads) > 10:
            text += f"...и ещё {len(ads) - 10} объявлений"

    await callback.message.edit_text(text, reply_markup=get_ads_keyboard(), parse_mode="HTML")
    await callback.answer()


# ====== ЛОГИ ======

@admin_router.callback_query(F.data == "admin_logs")
async def show_logs_menu(callback: CallbackQuery):
    """Показать меню логов"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return

    text = "📋 <b>Логи системы</b>\n\nВыберите категорию:"
    await callback.message.edit_text(text, reply_markup=get_logs_keyboard(), parse_mode="HTML")
    await callback.answer()


@admin_router.callback_query(F.data.startswith("logs_"))
async def show_logs_list(callback: CallbackQuery):
    """Показать список логов"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return

    action = callback.data.split("_", 1)[1]

    # Определяем фильтры
    limit = 50
    log_type = None

    if action == "latest_50":
        limit = 50
        title = "📋 Последние 50 логов"
    elif action == "latest_100":
        limit = 100
        title = "📋 Последние 100 логов"
    elif action == "published":
        log_type = "ad_published"
        title = "✅ Опубликованные объявления"
    elif action == "rejected":
        log_type = "ad_rejected"
        title = "❌ Отклоненные объявления"
    else:
        title = "📋 Логи"

    # Получаем логи
    logs = db.get_logs(limit=limit, log_type=log_type)

    if not logs:
        text = f"{title}\n\nЛогов не найдено"
    else:
        text = f"<b>{title}</b>\n\n"

        for i, log in enumerate(logs[:15], 1):
            text += f"{i}. [{log['log_type']}] {log['message']}\n"
            text += f"   {log['created_at']}\n\n"

        if len(logs) > 15:
            text += f"...и ещё {len(logs) - 15} записей"

    await callback.message.edit_text(text, reply_markup=get_logs_keyboard(), parse_mode="HTML")
    await callback.answer()


# ====== РАССЫЛКА ======

@admin_router.callback_query(F.data == "admin_broadcast")
async def start_broadcast(callback: CallbackQuery, state: FSMContext):
    """Начать создание рассылки"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return

    users_stats = db.get_users_count()

    text = (
        "📢 <b>Создание рассылки</b>\n\n"
        f"Сообщение будет отправлено {users_stats['active']} активным пользователям.\n\n"
        "Отправьте текст сообщения для рассылки:"
    )

    await callback.message.edit_text(text, parse_mode="HTML")
    await state.set_state(BroadcastStates.waiting_message)
    await callback.answer()


@admin_router.message(BroadcastStates.waiting_message)
async def receive_broadcast_message(message: Message, state: FSMContext):
    """Получение текста рассылки"""
    if not is_admin(message.from_user.id):
        return

    # Сохраняем текст рассылки
    await state.update_data(broadcast_text=message.text)

    users_stats = db.get_users_count()

    text = (
        "📢 <b>Подтверждение рассылки</b>\n\n"
        f"Будет отправлено: {users_stats['active']} пользователям\n\n"
        "<b>Текст сообщения:</b>\n"
        f"{message.text}\n\n"
        "Отправить рассылку?"
    )

    await message.answer(text, reply_markup=get_broadcast_confirm_keyboard(), parse_mode="HTML")
    await state.set_state(BroadcastStates.confirm_broadcast)


@admin_router.callback_query(F.data == "broadcast_confirm", BroadcastStates.confirm_broadcast)
async def confirm_broadcast(callback: CallbackQuery, state: FSMContext):
    """Подтверждение и отправка рассылки"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return

    # Получаем текст рассылки
    data = await state.get_data()
    broadcast_text = data.get('broadcast_text')

    if not broadcast_text:
        await callback.answer("❌ Ошибка: текст рассылки не найден", show_alert=True)
        await state.clear()
        return

    # Получаем список активных пользователей
    users = db.get_all_users(only_active=True)
    total_users = len(users)

    if total_users == 0:
        await callback.message.edit_text("❌ Нет активных пользователей для рассылки")
        await state.clear()
        return

    # Создаем запись о рассылке
    broadcast_id = db.create_broadcast(
        admin_id=callback.from_user.id,
        message_text=broadcast_text,
        total_users=total_users
    )

    # Уведомляем о начале
    await callback.message.edit_text(
        f"📢 Рассылка начата...\n\nОтправка 0/{total_users}"
    )

    # Получаем bot из callback
    from aiogram import Bot
    bot_instance = callback.bot

    # Отправляем сообщения
    sent_count = 0
    failed_count = 0

    for user in users:
        try:
            await bot_instance.send_message(chat_id=user['tg_id'], text=broadcast_text)
            sent_count += 1

            # Обновляем прогресс каждые 10 сообщений
            if sent_count % 10 == 0:
                try:
                    await callback.message.edit_text(
                        f"📢 Рассылка в процессе...\n\n"
                        f"Отправлено: {sent_count}/{total_users}\n"
                        f"Ошибок: {failed_count}"
                    )
                except:
                    pass

            # Задержка, чтобы не превысить лимиты Telegram
            await asyncio.sleep(0.05)

        except Exception as e:
            failed_count += 1
            logger.error(f"Ошибка при отправке пользователю {user['tg_id']}: {e}")

            # Если пользователь заблокировал бота
            if "bot was blocked" in str(e).lower():
                db.block_user(user['tg_id'])

    # Обновляем статистику рассылки
    db.update_broadcast_stats(broadcast_id, sent_count, failed_count)
    db.complete_broadcast(broadcast_id)

    # Логируем
    db.add_log(
        log_type="broadcast",
        message=f"Рассылка завершена: отправлено {sent_count}, ошибок {failed_count}",
        tg_id=callback.from_user.id
    )

    # Итоговое сообщение
    text = (
        "✅ <b>Рассылка завершена!</b>\n\n"
        f"Отправлено: {sent_count}\n"
        f"Ошибок: {failed_count}\n"
        f"Всего пользователей: {total_users}"
    )

    await callback.message.edit_text(text, reply_markup=get_back_to_menu_keyboard(), parse_mode="HTML")
    await state.clear()
    await callback.answer()


@admin_router.callback_query(F.data == "broadcast_cancel", BroadcastStates.confirm_broadcast)
async def cancel_broadcast(callback: CallbackQuery, state: FSMContext):
    """Отмена рассылки"""
    await callback.message.edit_text("❌ Рассылка отменена", reply_markup=get_back_to_menu_keyboard())
    await state.clear()
    await callback.answer()


# ====== ИСТОРИЯ РАССЫЛОК ======

@admin_router.callback_query(F.data == "admin_broadcast_history")
async def show_broadcast_history(callback: CallbackQuery):
    """Показать историю рассылок"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return

    broadcasts = db.get_broadcasts(limit=10)

    if not broadcasts:
        text = "📜 <b>История рассылок</b>\n\nРассылок пока не было"
    else:
        text = "📜 <b>История рассылок</b>\n\n"

        for i, broadcast in enumerate(broadcasts, 1):
            status = "✅" if broadcast['status'] == 'completed' else "⏳"
            text += f"{i}. {status} {broadcast['created_at']}\n"
            text += f"   Отправлено: {broadcast['sent_count']}/{broadcast['total_users']}\n"
            text += f"   Ошибок: {broadcast['failed_count']}\n\n"

    await callback.message.edit_text(text, reply_markup=get_back_to_menu_keyboard(), parse_mode="HTML")
    await callback.answer()