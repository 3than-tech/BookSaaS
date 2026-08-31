"""Telegram Bot с админ панелью для BookSaaS"""
import asyncio
import sqlite3
import logging
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# Конфигурация
BOT_TOKEN = 'ВАШ_TELEGRAM_BOT_TOKEN'
ADMIN_USER_ID = 
DATABASE = 'booksaas.db'

# Логирование
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Состояния для FSM
class AdminStates(StatesGroup):
    view_menu = State()
    view_users = State()
    user_detail = State()
    edit_user = State()
    view_analytics = State()
    manage_subscription = State()

# Инициализация
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

def get_db():
    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row
    return db

async def check_admin(user_id: int) -> bool:
    """Проверка прав администратора"""
    return user_id == ADMIN_USER_ID

def format_user_info(user):
    """Форматирование информации пользователя"""
    created = datetime.fromisoformat(user['created_at'].replace('Z', ''))
    
    trial_end = None
    if user['trial_ends_at']:
        trial_end = datetime.fromisoformat(user['trial_ends_at'].replace('Z', ''))
    
    days_left = 'N/A'
    if trial_end:
        days_left = (trial_end.date() - datetime.now().date()).days
    
    return f"""
📊 <b>{user['name']}</b>
├ ID: <code>{user['id']}</code>
├ Username: @{user['username']}
├ Email: {user['email'] or 'Не указан'}
├ Phone: {user['phone'] or 'Не указан'}
├ Рейтинг: ⭐ {user['rating']:.1f}
├ Подписка: {user['subscription_status']}
├ Дней осталось: {days_left}
├ Создан: {created.strftime('%d.%m.%Y %H:%M')}
└ Реферальный код: {user['referral_code']}
"""

# ── ОСНОВНЫЕ КОМАНДЫ ──────────────────────────────────────────────
@dp.message(Command('start'))
async def cmd_start(message: types.Message, state: FSMContext):
    """Стартовая команда"""
    if not await check_admin(message.from_user.id):
        await message.answer('❌ Доступ запрещен. Вы не администратор.')
        return
    
    await state.set_state(AdminStates.view_menu)
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text='👥 Пользователи', callback_data='view_users')],
        [types.InlineKeyboardButton(text='📊 Аналитика', callback_data='view_analytics')],
        [types.InlineKeyboardButton(text='🔧 Управление', callback_data='manage_menu')],
        [types.InlineKeyboardButton(text='💰 Финансы', callback_data='view_finances')],
    ])
    
    await message.answer(
        f'👋 <b>Добро пожаловать в админ панель BookSaaS</b>\n\n'
        f'Выберите действие:',
        reply_markup=keyboard,
        parse_mode='HTML'
    )

# ── ПОЛЬЗОВАТЕЛИ ──────────────────────────────────────────────────
@dp.callback_query(F.data == 'view_users')
async def view_users(callback: types.CallbackQuery, state: FSMContext):
    """Показать список пользователей"""
    await callback.answer()
    
    db = get_db()
    users = db.execute('''
        SELECT id, username, name, email, subscription_status, rating, created_at
        FROM masters
        ORDER BY created_at DESC
        LIMIT 20
    ''').fetchall()
    
    text = f'<b>👥 Всего пользователей: {len(users)}</b>\n\n'
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[])
    
    for user in users:
        status_emoji = '✅' if user['subscription_status'] == 'active' else '⏰' if user['subscription_status'] == 'trial' else '❌'
        text += f"{status_emoji} <b>{user['name']}</b> (@{user['username']})\n"
        text += f"   📧 {user['email'] or 'N/A'} | ⭐ {user['rating']:.1f}\n"
        
        keyboard.inline_keyboard.append([
            types.InlineKeyboardButton(
                text=f'📋 {user["name"]}',
                callback_data=f'user_detail:{user["id"]}'
            )
        ])
    
    keyboard.inline_keyboard.append([
        types.InlineKeyboardButton(text='🔙 Назад', callback_data='back_to_menu')
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode='HTML')
    await state.set_state(AdminStates.view_users)

@dp.callback_query(F.data.startswith('user_detail:'))
async def user_detail(callback: types.CallbackQuery, state: FSMContext):
    """Просмотр деталей пользователя"""
    await callback.answer()
    
    user_id = callback.data.split(':')[1]
    db = get_db()
    user = db.execute('SELECT * FROM masters WHERE id=?', [user_id]).fetchone()
    
    if not user:
        await callback.answer('❌ Пользователь не найден', show_alert=True)
        return
    
    user = dict(user)
    text = format_user_info(user)
    
    # Статистика заказов
    bookings = db.execute(
        'SELECT COUNT(*) as cnt FROM bookings WHERE master_id=?',
        [user_id]
    ).fetchone()['cnt']
    
    reviews = db.execute(
        'SELECT AVG(rating) as avg FROM reviews WHERE master_id=?',
        [user_id]
    ).fetchone()
    
    text += f"\n📈 <b>Статистика:</b>\n"
    text += f"├ Заказов: {bookings}\n"
    text += f"└ Средняя оценка: {reviews['avg']:.1f if reviews['avg'] else 'N/A'}\n"
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text='✏️ Редактировать', callback_data=f'edit_user:{user_id}')],
        [types.InlineKeyboardButton(text='💳 Управление подпиской', callback_data=f'sub_manage:{user_id}')],
        [types.InlineKeyboardButton(text='🗑️ Удалить', callback_data=f'delete_user:{user_id}')],
        [types.InlineKeyboardButton(text='🔙 Назад', callback_data='view_users')],
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode='HTML')
    await state.set_state(AdminStates.user_detail)

@dp.callback_query(F.data.startswith('edit_user:'))
async def edit_user(callback: types.CallbackQuery, state: FSMContext):
    """Редактирование пользователя"""
    await callback.answer()
    
    user_id = callback.data.split(':')[1]
    db = get_db()
    user = db.execute('SELECT * FROM masters WHERE id=?', [user_id]).fetchone()
    
    if not user:
        await callback.answer('❌ Пользователь не найден', show_alert=True)
        return
    
    text = f"""<b>✏️ Редактирование пользователя</b>\n
<code>{user['name']}</code>\n
Выберите поле для редактирования:
"""
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text='📝 Имя', callback_data=f'edit_name:{user_id}')],
        [types.InlineKeyboardButton(text='📧 Email', callback_data=f'edit_email:{user_id}')],
        [types.InlineKeyboardButton(text='📱 Телефон', callback_data=f'edit_phone:{user_id}')],
        [types.InlineKeyboardButton(text='⭐ Рейтинг', callback_data=f'edit_rating:{user_id}')],
        [types.InlineKeyboardButton(text='🔙 Назад', callback_data=f'user_detail:{user_id}')],
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode='HTML')
    await state.set_state(AdminStates.edit_user)

@dp.callback_query(F.data.startswith('sub_manage:'))
async def manage_subscription(callback: types.CallbackQuery, state: FSMContext):
    """Управление подпиской"""
    await callback.answer()
    
    user_id = callback.data.split(':')[1]
    db = get_db()
    user = db.execute('SELECT * FROM masters WHERE id=?', [user_id]).fetchone()
    
    if not user:
        await callback.answer('❌ Пользователь не найден', show_alert=True)
        return
    
    user = dict(user)
    text = f"""<b>💳 Управление подпиской</b>\n\n
👤 {user['name']}
Текущий статус: <b>{user['subscription_status']}</b>\n

Выберите действие:
"""
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text='✅ Активировать', callback_data=f'activate_sub:{user_id}')],
        [types.InlineKeyboardButton(text='⏸️ Продлить пробный', callback_data=f'extend_trial:{user_id}')],
        [types.InlineKeyboardButton(text='❌ Прервать', callback_data=f'expire_sub:{user_id}')],
        [types.InlineKeyboardButton(text='🔙 Назад', callback_data=f'user_detail:{user_id}')],
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode='HTML')
    await state.set_state(AdminStates.manage_subscription)

@dp.callback_query(F.data.startswith('activate_sub:'))
async def activate_subscription(callback: types.CallbackQuery):
    """Активировать подписку"""
    await callback.answer()
    
    user_id = callback.data.split(':')[1]
    db = get_db()
    
    db.execute(
        'UPDATE masters SET subscription_status=? WHERE id=?',
        ['active', user_id]
    )
    db.commit()
    
    await callback.answer('✅ Подписка активирована', show_alert=True)
    await callback.message.delete()

@dp.callback_query(F.data.startswith('extend_trial:'))
async def extend_trial(callback: types.CallbackQuery):
    """Продлить пробный период на 14 дней"""
    await callback.answer()
    
    user_id = callback.data.split(':')[1]
    db = get_db()
    
    new_end = datetime.now() + timedelta(days=14)
    db.execute(
        'UPDATE masters SET trial_ends_at=?, subscription_status=? WHERE id=?',
        [new_end.isoformat(), 'trial', user_id]
    )
    db.commit()
    
    await callback.answer('⏰ Пробный период продлен на 14 дней', show_alert=True)
    await callback.message.delete()

@dp.callback_query(F.data.startswith('expire_sub:'))
async def expire_subscription(callback: types.CallbackQuery):
    """Закончить подписку"""
    await callback.answer()
    
    user_id = callback.data.split(':')[1]
    db = get_db()
    
    db.execute(
        'UPDATE masters SET subscription_status=? WHERE id=?',
        ['expired', user_id]
    )
    db.commit()
    
    await callback.answer('❌ Подписка остановлена', show_alert=True)
    await callback.message.delete()

# ── АНАЛИТИКА ────────────────────────────────────────────────────
@dp.callback_query(F.data == 'view_analytics')
async def view_analytics(callback: types.CallbackQuery, state: FSMContext):
    """Показать аналитику"""
    await callback.answer()
    
    db = get_db()
    
    # Общая статистика
    total_users = db.execute('SELECT COUNT(*) as cnt FROM masters').fetchone()['cnt']
    active_users = db.execute(
        'SELECT COUNT(*) as cnt FROM masters WHERE subscription_status=?',
        ['active']
    ).fetchone()['cnt']
    trial_users = db.execute(
        'SELECT COUNT(*) as cnt FROM masters WHERE subscription_status=?',
        ['trial']
    ).fetchone()['cnt']
    
    # Заказы за день
    today = datetime.now().date()
    today_bookings = db.execute(
        'SELECT COUNT(*) as cnt FROM bookings WHERE date=?',
        [str(today)]
    ).fetchone()['cnt']
    
    # Доход за месяц
    month_start = today.replace(day=1)
    month_income = db.execute('''
        SELECT SUM(amount) as total FROM transactions 
        WHERE type='income' AND date(created_at) >= ?
    ''', [str(month_start)]).fetchone()['total'] or 0
    
    # Средний рейтинг
    avg_rating = db.execute(
        'SELECT AVG(rating) as avg FROM masters WHERE rating > 0'
    ).fetchone()['avg'] or 0
    
    text = f"""<b>📊 Аналитика BookSaaS</b>\n
👥 <b>Пользователи:</b>
├ Всего: {total_users}
├ Активные подписки: {active_users}
├ На пробном периоде: {trial_users}
└ Истекла подписка: {total_users - active_users - trial_users}\n

📅 <b>Сегодня ({today}):</b>
└ Заказов: {today_bookings}\n

💰 <b>Финансы (текущий месяц):</b>
└ Доход: {month_income:.2f} ₽\n

⭐ <b>Средний рейтинг мастеров:</b> {avg_rating:.2f}
"""
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text='💹 Детальная статистика', callback_data='detailed_stats')],
        [types.InlineKeyboardButton(text='🔙 Назад', callback_data='back_to_menu')],
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode='HTML')
    await state.set_state(AdminStates.view_analytics)

@dp.callback_query(F.data == 'detailed_stats')
async def detailed_stats(callback: types.CallbackQuery):
    """Подробная статистика"""
    await callback.answer()
    
    db = get_db()
    today = datetime.now().date()
    
    # Топ мастеров по заказам
    top_masters = db.execute('''
        SELECT masters.name, COUNT(bookings.id) as cnt
        FROM masters
        LEFT JOIN bookings ON masters.id=bookings.master_id
        GROUP BY masters.id
        ORDER BY cnt DESC
        LIMIT 5
    ''').fetchall()
    
    text = '<b>📈 Подробная статистика</b>\n\n'
    text += '<b>🏆 Топ мастеров по заказам:</b>\n'
    
    for i, master in enumerate(top_masters, 1):
        text += f'{i}. {master["name"]}: {master["cnt"]} заказов\n'
    
    # Статус заказов
    pending = db.execute(
        'SELECT COUNT(*) as cnt FROM bookings WHERE status=?',
        ['pending']
    ).fetchone()['cnt']
    confirmed = db.execute(
        'SELECT COUNT(*) as cnt FROM bookings WHERE status=?',
        ['confirmed']
    ).fetchone()['cnt']
    completed = db.execute(
        'SELECT COUNT(*) as cnt FROM bookings WHERE status=?',
        ['completed']
    ).fetchone()['cnt']
    
    text += f'\n<b>📋 Статусы заказов:</b>\n'
    text += f'⏳ Ожидают: {pending}\n'
    text += f'✅ Подтверждены: {confirmed}\n'
    text += f'✔️ Завершены: {completed}\n'
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text='🔙 Назад', callback_data='view_analytics')],
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode='HTML')

# ── НАВИГАЦИЯ ────────────────────────────────────────────────────
@dp.callback_query(F.data == 'back_to_menu')
async def back_to_menu(callback: types.CallbackQuery, state: FSMContext):
    """Вернуться в главное меню"""
    await callback.answer()
    await state.set_state(AdminStates.view_menu)
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text='👥 Пользователи', callback_data='view_users')],
        [types.InlineKeyboardButton(text='📊 Аналитика', callback_data='view_analytics')],
        [types.InlineKeyboardButton(text='🔧 Управление', callback_data='manage_menu')],
        [types.InlineKeyboardButton(text='💰 Финансы', callback_data='view_finances')],
    ])
    
    await callback.message.edit_text(
        '👋 <b>Админ панель BookSaaS</b>\n\nВыберите действие:',
        reply_markup=keyboard,
        parse_mode='HTML'
    )

@dp.callback_query(F.data.startswith('manage_menu'))
async def manage_menu(callback: types.CallbackQuery):
    """Меню управления"""
    await callback.answer()
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text='📢 Отправить рассылку', callback_data='send_broadcast')],
        [types.InlineKeyboardButton(text='🗑️ Очистить БД (ОСТОРОЖНО!)', callback_data='clear_db_confirm')],
        [types.InlineKeyboardButton(text='🔙 Назад', callback_data='back_to_menu')],
    ])
    
    await callback.message.edit_text(
        '<b>🔧 Управление</b>\n\nВыберите действие:',
        reply_markup=keyboard,
        parse_mode='HTML'
    )

@dp.callback_query(F.data == 'view_finances')
async def view_finances(callback: types.CallbackQuery):
    """Финансовая статистика"""
    await callback.answer()
    
    db = get_db()
    today = datetime.now().date()
    
    # Доход за день
    day_income = db.execute('''
        SELECT SUM(amount) as total FROM transactions 
        WHERE type='income' AND date(created_at)=?
    ''', [str(today)]).fetchone()['total'] or 0
    
    # Доход за неделю
    week_start = today - timedelta(days=today.weekday())
    week_income = db.execute('''
        SELECT SUM(amount) as total FROM transactions 
        WHERE type='income' AND date(created_at) >= ?
    ''', [str(week_start)]).fetchone()['total'] or 0
    
    # Доход за месяц
    month_start = today.replace(day=1)
    month_income = db.execute('''
        SELECT SUM(amount) as total FROM transactions 
        WHERE type='income' AND date(created_at) >= ?
    ''', [str(month_start)]).fetchone()['total'] or 0
    
    # Расходы за месяц
    expenses = db.execute('''
        SELECT SUM(amount) as total FROM transactions 
        WHERE type='expense' AND date(created_at) >= ?
    ''', [str(month_start)]).fetchone()['total'] or 0
    
    text = f"""<b>💰 Финансовая статистика</b>\n
📊 <b>Доходы:</b>
├ Сегодня: {day_income:.2f} ₽
├ Неделя: {week_income:.2f} ₽
└ Месяц: {month_income:.2f} ₽\n

💸 <b>Расходы за месяц:</b> {expenses:.2f} ₽\n

📈 <b>Чистый доход (месяц):</b> {month_income - expenses:.2f} ₽
"""
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text='🔙 Назад', callback_data='back_to_menu')],
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode='HTML')

# ── ОБРАБОТЧИК НЕИЗВЕСТНЫХ КОМАНД ────────────────────────────────
@dp.message(StateFilter(None))
async def unknown_command(message: types.Message):
    """Обработка неизвестных команд"""
    if not await check_admin(message.from_user.id):
        await message.answer('❌ Доступ запрещен.')
        return
    
    await message.answer('ℹ️ Используйте /start для открытия админ панели')

async def main():
    """Запуск бота"""
    logger.info('🤖 Бот запущен...')
    await dp.start_polling(bot, allowed_updates=['message', 'callback_query'])

if __name__ == '__main__':
    asyncio.run(main())
