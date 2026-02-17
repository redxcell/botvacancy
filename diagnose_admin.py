"""
Скрипт для диагностики проблем с админ-панелью
Запустите: python diagnose_admin.py
"""

import sys
import os

print("=" * 60)
print("🔍 ДИАГНОСТИКА АДМИН-ПАНЕЛИ")
print("=" * 60)

# Проверка 1: Импорты
print("\n1️⃣ Проверка импортов...")
try:
    from admin_panel import ADMIN_IDS, admin_router
    print("   ✅ admin_panel.py импортирован успешно")
except Exception as e:
    print(f"   ❌ Ошибка импорта admin_panel.py: {e}")
    sys.exit(1)

try:
    from database import db
    print("   ✅ database.py импортирован успешно")
except Exception as e:
    print(f"   ❌ Ошибка импорта database.py: {e}")
    sys.exit(1)

try:
    from config import config
    print("   ✅ config.py импортирован успешно")
except Exception as e:
    print(f"   ❌ Ошибка импорта config.py: {e}")
    sys.exit(1)

# Проверка 2: ADMIN_IDS
print("\n2️⃣ Проверка ADMIN_IDS...")
if not ADMIN_IDS or ADMIN_IDS == []:
    print("   ⚠️  ADMIN_IDS пуст! Добавьте свой Telegram ID в admin_panel.py")
    print("   Откройте admin_panel.py и найдите:")
    print("   ADMIN_IDS = [")
    print("       123456789,  # ← Замените на свой ID")
    print("   ]")
else:
    print(f"   ✅ ADMIN_IDS содержит {len(ADMIN_IDS)} ID:")
    for admin_id in ADMIN_IDS:
        print(f"      - {admin_id}")

# Проверка 3: База данных
print("\n3️⃣ Проверка базы данных...")
try:
    # Проверяем, что БД создается
    users_count = db.get_users_count()
    print(f"   ✅ База данных работает")
    print(f"      Пользователей: {users_count['total']}")
    
    if users_count['total'] == 0:
        print("   ℹ️  В базе данных пока нет пользователей")
        print("      Отправьте боту /start для регистрации")
except Exception as e:
    print(f"   ❌ Ошибка при работе с БД: {e}")

# Проверка 4: Роутер
print("\n4️⃣ Проверка регистрации обработчиков...")
try:
    # Получаем список обработчиков в роутере
    handlers_count = len(admin_router.observers['message']) + len(admin_router.observers['callback_query'])
    print(f"   ✅ Админ-роутер содержит {handlers_count} обработчиков")
    
    # Проверяем callback_query обработчики
    callback_handlers = admin_router.observers.get('callback_query', [])
    if callback_handlers:
        print(f"   ✅ Callback обработчиков: {len(callback_handlers)}")
    else:
        print("   ⚠️  Нет callback обработчиков!")
        
except Exception as e:
    print(f"   ⚠️  Не удалось проверить обработчики: {e}")

# Проверка 5: Токен бота
print("\n5️⃣ Проверка конфигурации...")
if config.BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
    print("   ❌ BOT_TOKEN не установлен в .env или config.py")
else:
    print("   ✅ BOT_TOKEN установлен")

# Проверка 6: Файл main.py
print("\n6️⃣ Проверка main.py...")
try:
    with open('main.py', 'r', encoding='utf-8') as f:
        content = f.read()
        
    if 'from admin_panel import admin_router' in content:
        print("   ✅ admin_panel импортирован в main.py")
    else:
        print("   ❌ admin_panel НЕ импортирован в main.py!")
        print("   Добавьте: from admin_panel import admin_router, ADMIN_IDS")
    
    if 'dp.include_router(admin_router)' in content:
        print("   ✅ admin_router зарегистрирован в диспетчере")
    else:
        print("   ❌ admin_router НЕ зарегистрирован!")
        print("   Добавьте: dp.include_router(admin_router)")
        
except FileNotFoundError:
    print("   ❌ Файл main.py не найден")
except Exception as e:
    print(f"   ❌ Ошибка при чтении main.py: {e}")

# Итоги
print("\n" + "=" * 60)
print("📋 ИТОГИ ДИАГНОСТИКИ")
print("=" * 60)

if not ADMIN_IDS or ADMIN_IDS == []:
    print("❌ КРИТИЧНО: Добавьте свой Telegram ID в ADMIN_IDS")
    print("   1. Узнайте свой ID через бота @userinfobot")
    print("   2. Откройте admin_panel.py")
    print("   3. Найдите ADMIN_IDS = [] и добавьте свой ID")
    print("   4. Перезапустите бота")
else:
    print("✅ Админ-панель настроена")
    print("\n📝 Как использовать:")
    print("   1. Запустите бота: python main.py")
    print("   2. Отправьте боту /start (чтобы зарегистрироваться)")
    print("   3. Отправьте боту /admin")
    print("   4. Нажимайте на кнопки")
    print("\n🐛 Если кнопки не работают:")
    print("   1. Проверьте логи: tail -f bot.log")
    print("   2. Убедитесь, что ваш ID в списке ADMIN_IDS")
    print("   3. Перезапустите бота")

print("\n" + "=" * 60)
