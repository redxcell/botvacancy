"""
Модели базы данных для бота
SQLite база данных с таблицами: users, ads, logs
"""

import sqlite3
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class Database:
    """Класс для работы с базой данных SQLite"""
    
    def __init__(self, db_path: str = "bot_database.db"):
        """
        Инициализация базы данных
        
        Args:
            db_path: Путь к файлу базы данных
        """
        self.db_path = db_path
        self.create_tables()
    
    @contextmanager
    def get_connection(self):
        """Контекстный менеджер для работы с соединением"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Ошибка при работе с БД: {e}")
            raise
        finally:
            conn.close()
    
    def create_tables(self):
        """Создание таблиц в базе данных"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Таблица пользователей
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tg_id INTEGER UNIQUE NOT NULL,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    is_subscribed BOOLEAN DEFAULT 1,
                    is_blocked BOOLEAN DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Индекс для быстрого поиска по tg_id
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_users_tg_id 
                ON users(tg_id)
            """)
            
            # Таблица объявлений
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    tg_id INTEGER NOT NULL,
                    username TEXT,
                    ad_text TEXT NOT NULL,
                    ad_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    rejection_reason TEXT,
                    message_id INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            """)
            
            # Индексы для объявлений
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_ads_user_id 
                ON ads(user_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_ads_status 
                ON ads(status)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_ads_created_at 
                ON ads(created_at)
            """)
            
            # Таблица логов
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    log_type TEXT NOT NULL,
                    user_id INTEGER,
                    tg_id INTEGER,
                    message TEXT NOT NULL,
                    details TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Индекс для логов
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_logs_created_at 
                ON logs(created_at)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_logs_type 
                ON logs(log_type)
            """)
            
            # Таблица рассылок
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS broadcasts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    admin_id INTEGER NOT NULL,
                    message_text TEXT NOT NULL,
                    total_users INTEGER DEFAULT 0,
                    sent_count INTEGER DEFAULT 0,
                    failed_count INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP
                )
            """)
            
            conn.commit()
            logger.info("Таблицы базы данных успешно созданы")
    
    # ========== РАБОТА С ПОЛЬЗОВАТЕЛЯМИ ==========
    
    def add_user(self, tg_id: int, username: Optional[str] = None, 
                 first_name: Optional[str] = None, last_name: Optional[str] = None) -> int:
        """
        Добавление нового пользователя или обновление существующего
        
        Returns:
            ID пользователя в базе данных
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Проверяем, существует ли пользователь
            cursor.execute("SELECT id FROM users WHERE tg_id = ?", (tg_id,))
            existing_user = cursor.fetchone()
            
            if existing_user:
                # Обновляем данные существующего пользователя
                cursor.execute("""
                    UPDATE users 
                    SET username = ?, first_name = ?, last_name = ?, 
                        last_activity = CURRENT_TIMESTAMP
                    WHERE tg_id = ?
                """, (username, first_name, last_name, tg_id))
                return existing_user['id']
            else:
                # Добавляем нового пользователя
                cursor.execute("""
                    INSERT INTO users (tg_id, username, first_name, last_name)
                    VALUES (?, ?, ?, ?)
                """, (tg_id, username, first_name, last_name))
                return cursor.lastrowid
    
    def get_user_by_tg_id(self, tg_id: int) -> Optional[Dict[str, Any]]:
        """Получение пользователя по Telegram ID"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE tg_id = ?", (tg_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def update_user_subscription(self, tg_id: int, is_subscribed: bool):
        """Обновление статуса подписки пользователя"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE users SET is_subscribed = ?, last_activity = CURRENT_TIMESTAMP
                WHERE tg_id = ?
            """, (is_subscribed, tg_id))
    
    def block_user(self, tg_id: int):
        """Блокировка пользователя"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET is_blocked = 1 WHERE tg_id = ?", (tg_id,))
    
    def get_all_users(self, only_subscribed: bool = False, 
                      only_active: bool = False) -> List[Dict[str, Any]]:
        """
        Получение всех пользователей
        
        Args:
            only_subscribed: Только подписанные пользователи
            only_active: Только не заблокированные пользователи
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            query = "SELECT * FROM users WHERE 1=1"
            params = []
            
            if only_subscribed:
                query += " AND is_subscribed = 1"
            
            if only_active:
                query += " AND is_blocked = 0"
            
            query += " ORDER BY created_at DESC"
            
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]
    
    def get_users_count(self) -> Dict[str, int]:
        """Получение статистики по пользователям"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("SELECT COUNT(*) as total FROM users")
            total = cursor.fetchone()['total']
            
            cursor.execute("SELECT COUNT(*) as subscribed FROM users WHERE is_subscribed = 1")
            subscribed = cursor.fetchone()['subscribed']
            
            cursor.execute("SELECT COUNT(*) as blocked FROM users WHERE is_blocked = 1")
            blocked = cursor.fetchone()['blocked']
            
            return {
                'total': total,
                'subscribed': subscribed,
                'blocked': blocked,
                'active': total - blocked
            }
    
    # ========== РАБОТА С ОБЪЯВЛЕНИЯМИ ==========
    
    def add_ad(self, tg_id: int, username: Optional[str], ad_text: str, 
               ad_type: str, status: str, rejection_reason: Optional[str] = None,
               message_id: Optional[int] = None) -> int:
        """
        Добавление объявления
        
        Args:
            tg_id: Telegram ID пользователя
            username: Username пользователя
            ad_text: Текст объявления
            ad_type: Тип (resume/vacancy)
            status: Статус (published/rejected)
            rejection_reason: Причина отклонения
            message_id: ID сообщения в канале
        
        Returns:
            ID объявления
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Получаем user_id
            user = self.get_user_by_tg_id(tg_id)
            user_id = user['id'] if user else None
            
            cursor.execute("""
                INSERT INTO ads (user_id, tg_id, username, ad_text, ad_type, 
                                status, rejection_reason, message_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (user_id, tg_id, username, ad_text, ad_type, status, 
                  rejection_reason, message_id))
            
            return cursor.lastrowid
    
    def get_ads(self, limit: int = 100, offset: int = 0, 
                status: Optional[str] = None, 
                ad_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Получение объявлений с фильтрацией
        
        Args:
            limit: Лимит записей
            offset: Смещение
            status: Фильтр по статусу
            ad_type: Фильтр по типу
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            query = "SELECT * FROM ads WHERE 1=1"
            params = []
            
            if status:
                query += " AND status = ?"
                params.append(status)
            
            if ad_type:
                query += " AND ad_type = ?"
                params.append(ad_type)
            
            query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])
            
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]
    
    def get_user_ads(self, tg_id: int, limit: int = 20) -> List[Dict[str, Any]]:
        """Получение объявлений конкретного пользователя"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM ads 
                WHERE tg_id = ? 
                ORDER BY created_at DESC 
                LIMIT ?
            """, (tg_id, limit))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_ads_stats(self) -> Dict[str, int]:
        """Получение статистики по объявлениям"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("SELECT COUNT(*) as total FROM ads")
            total = cursor.fetchone()['total']
            
            cursor.execute("SELECT COUNT(*) as published FROM ads WHERE status = 'published'")
            published = cursor.fetchone()['published']
            
            cursor.execute("SELECT COUNT(*) as rejected FROM ads WHERE status = 'rejected'")
            rejected = cursor.fetchone()['rejected']
            
            cursor.execute("SELECT COUNT(*) as resumes FROM ads WHERE ad_type = 'resume'")
            resumes = cursor.fetchone()['resumes']
            
            cursor.execute("SELECT COUNT(*) as vacancies FROM ads WHERE ad_type = 'vacancy'")
            vacancies = cursor.fetchone()['vacancies']
            
            return {
                'total': total,
                'published': published,
                'rejected': rejected,
                'resumes': resumes,
                'vacancies': vacancies
            }
    
    # ========== РАБОТА С ЛОГАМИ ==========
    
    def add_log(self, log_type: str, message: str, 
                tg_id: Optional[int] = None, 
                user_id: Optional[int] = None,
                details: Optional[str] = None):
        """
        Добавление записи в лог
        
        Args:
            log_type: Тип лога (start, ad_published, ad_rejected, error, etc.)
            message: Сообщение лога
            tg_id: Telegram ID пользователя
            user_id: ID пользователя в БД
            details: Дополнительные детали
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO logs (log_type, user_id, tg_id, message, details)
                VALUES (?, ?, ?, ?, ?)
            """, (log_type, user_id, tg_id, message, details))
    
    def get_logs(self, limit: int = 100, offset: int = 0,
                 log_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Получение логов
        
        Args:
            limit: Лимит записей
            offset: Смещение
            log_type: Фильтр по типу лога
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            query = "SELECT * FROM logs WHERE 1=1"
            params = []
            
            if log_type:
                query += " AND log_type = ?"
                params.append(log_type)
            
            query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])
            
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]
    
    # ========== РАБОТА С РАССЫЛКАМИ ==========
    
    def create_broadcast(self, admin_id: int, message_text: str, 
                        total_users: int) -> int:
        """Создание новой рассылки"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO broadcasts (admin_id, message_text, total_users, status)
                VALUES (?, ?, ?, 'in_progress')
            """, (admin_id, message_text, total_users))
            return cursor.lastrowid
    
    def update_broadcast_stats(self, broadcast_id: int, sent_count: int, 
                              failed_count: int):
        """Обновление статистики рассылки"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE broadcasts 
                SET sent_count = ?, failed_count = ?
                WHERE id = ?
            """, (sent_count, failed_count, broadcast_id))
    
    def complete_broadcast(self, broadcast_id: int):
        """Завершение рассылки"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE broadcasts 
                SET status = 'completed', completed_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (broadcast_id,))
    
    def get_broadcasts(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Получение истории рассылок"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM broadcasts 
                ORDER BY created_at DESC 
                LIMIT ?
            """, (limit,))
            return [dict(row) for row in cursor.fetchall()]


# Создаем глобальный экземпляр базы данных
db = Database()
