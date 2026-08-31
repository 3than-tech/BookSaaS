import sqlite3, json, uuid, os, io, re, logging
from datetime import datetime, timedelta
from collections import defaultdict, Counter
from functools import wraps
import email_service as mail
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask import (Flask, render_template, request, redirect,
                   url_for, session, jsonify, g, flash, send_from_directory)
try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

app = Flask(__name__)
app.secret_key = 'booksaas-change-this-in-production-please'
DATABASE   = 'booksaas.db'
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), 'uploads')
os.makedirs(UPLOAD_DIR, exist_ok=True)

TRIAL_DAYS = mail.TRIAL_DAYS
MONTHLY_PRICE = mail.MONTHLY_PRICE
SUPPORT_URL = mail.SUPPORT_URL

@app.context_processor
def inject_globals():
    return {
        'trial_days': TRIAL_DAYS,
        'monthly_price': MONTHLY_PRICE,
        'support_url': SUPPORT_URL,
    }

MAX_IMAGE_BYTES = 8 * 1024 * 1024
ALLOWED_EXT = {'jpg', 'jpeg', 'png', 'webp', 'gif'}

THEMES = {
    'noir': {
        'id': 'noir', 'name': 'Noir',
        'masterBg': 'bg-zinc-950 text-zinc-100',
        'sidebarBg': 'bg-zinc-900 border-white/5',
        'clientBg': 'bg-zinc-950 text-zinc-100',
        'accentBg': 'bg-amber-400 text-zinc-950 hover:bg-amber-300',
        'accentText': 'text-amber-400', 'accentBorder': 'border-amber-400',
        'cardBg': 'bg-zinc-900 border-white/8', 'mutedText': 'text-zinc-400',
        'fontTitle': 'font-serif', 'dark': True,
        'gradient': 'from-zinc-950 via-zinc-950/60',
        'image': 'https://images.unsplash.com/photo-1503951914875-452162b0f3f1?q=80&w=800&auto=format&fit=crop',
        'services': [
            {'id': 's1', 'name': 'Мужская стрижка', 'duration': '1 ч', 'price': '1500'},
            {'id': 's2', 'name': 'Стрижка + Борода', 'duration': '1.5 ч', 'price': '2200'},
            {'id': 's3', 'name': 'Камуфляж седины', 'duration': '30 мин', 'price': '1000'},
        ],
    },
    'obsidian': {
        'id': 'obsidian', 'name': 'Obsidian',
        'masterBg': 'bg-black text-zinc-100', 'sidebarBg': 'bg-zinc-950 border-zinc-800',
        'clientBg': 'bg-black text-zinc-100',
        'accentBg': 'bg-red-500 text-white hover:bg-red-400',
        'accentText': 'text-red-400', 'accentBorder': 'border-red-500',
        'cardBg': 'bg-zinc-950 border-zinc-800', 'mutedText': 'text-zinc-500',
        'fontTitle': 'font-mono', 'dark': True,
        'gradient': 'from-black via-black/70',
        'image': 'https://images.unsplash.com/photo-1598371839696-5c5bb00bdc28?q=80&w=800&auto=format&fit=crop',
        'services': [
            {'id': 's1', 'name': 'Мини-тату', 'duration': '1 ч', 'price': '3000'},
            {'id': 's2', 'name': 'Сеанс (до 4 часов)', 'duration': '4 ч', 'price': '12000'},
            {'id': 's3', 'name': 'Разработка эскиза', 'duration': '1 ч', 'price': '1500'},
        ],
    },
    'blush': {
        'id': 'blush', 'name': 'Blush',
        'masterBg': 'bg-rose-50 text-stone-900', 'sidebarBg': 'bg-white border-rose-100',
        'clientBg': 'bg-gradient-to-b from-rose-100 to-rose-50 text-stone-900',
        'accentBg': 'bg-rose-500 text-white hover:bg-rose-600',
        'accentText': 'text-rose-500', 'accentBorder': 'border-rose-400',
        'cardBg': 'bg-white/80 border-rose-100 shadow-sm', 'mutedText': 'text-stone-400',
        'fontTitle': 'font-serif', 'dark': False,
        'gradient': 'from-rose-900/50 via-rose-900/20',
        'image': 'https://images.unsplash.com/photo-1562322140-8baeececf3df?q=80&w=800&auto=format&fit=crop',
        'services': [
            {'id': 's1', 'name': 'Женская стрижка', 'duration': '1.5 ч', 'price': '2500'},
            {'id': 's2', 'name': 'Сложное окрашивание', 'duration': '3 ч', 'price': '6000'},
            {'id': 's3', 'name': 'Укладка', 'duration': '1 ч', 'price': '1500'},
        ],
    },
    'sage': {
        'id': 'sage', 'name': 'Sage',
        'masterBg': 'bg-stone-50 text-stone-900', 'sidebarBg': 'bg-white border-stone-200',
        'clientBg': 'bg-gradient-to-b from-stone-100 to-stone-50 text-stone-900',
        'accentBg': 'bg-stone-800 text-white hover:bg-stone-700',
        'accentText': 'text-stone-700', 'accentBorder': 'border-stone-700',
        'cardBg': 'bg-white border-stone-200 shadow-sm', 'mutedText': 'text-stone-400',
        'fontTitle': 'font-serif', 'dark': False,
        'gradient': 'from-stone-900/60 via-stone-900/20',
        'image': 'https://images.unsplash.com/photo-1560066984-138dadb4c035?q=80&w=800&auto=format&fit=crop',
        'services': [
            {'id': 's1', 'name': 'Архитектура бровей', 'duration': '45 мин', 'price': '1200'},
            {'id': 's2', 'name': 'Ламинирование ресниц', 'duration': '1.5 ч', 'price': '2000'},
            {'id': 's3', 'name': 'Макияж вечерний', 'duration': '1.5 ч', 'price': '3500'},
        ],
    },
}

def init_db():
    """Инициализация БД с поддержкой отзывов, финансов, реферралов и уведомлений"""
    db = sqlite3.connect(DATABASE)
    db.execute('PRAGMA foreign_keys=ON')
    c = db.cursor()
    
    # Основные таблицы
    c.execute('''CREATE TABLE IF NOT EXISTS masters (
        id TEXT PRIMARY KEY,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        email TEXT,
        name TEXT NOT NULL,
        avatar TEXT,
        bio TEXT,
        phone TEXT,
        theme_id TEXT DEFAULT 'noir',
        location TEXT,
        services TEXT DEFAULT '[]',
        specialization TEXT,
        experience_years INTEGER DEFAULT 0,
        rating REAL DEFAULT 5.0,
        created_at TEXT,
        trial_started_at TEXT,
        trial_ends_at TEXT,
        subscription_status TEXT DEFAULT 'trial',
        referral_code TEXT UNIQUE,
        referral_earnings REAL DEFAULT 0
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS bookings (
        id TEXT PRIMARY KEY,
        master_id TEXT NOT NULL,
        client_name TEXT NOT NULL,
        client_phone TEXT NOT NULL,
        client_email TEXT,
        service_id TEXT,
        date TEXT NOT NULL,
        time TEXT NOT NULL,
        notes TEXT,
        status TEXT DEFAULT 'pending',
        created_at TEXT,
        FOREIGN KEY(master_id) REFERENCES masters(id)
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS clients (
        id TEXT PRIMARY KEY,
        master_id TEXT NOT NULL,
        name TEXT NOT NULL,
        phone TEXT NOT NULL,
        email TEXT,
        phone_key TEXT,
        tags TEXT DEFAULT '[]',
        created_at TEXT,
        FOREIGN KEY(master_id) REFERENCES masters(id)
    )''')
    
    # Новая таблица для отзывов
    c.execute('''CREATE TABLE IF NOT EXISTS reviews (
        id TEXT PRIMARY KEY,
        master_id TEXT NOT NULL,
        booking_id TEXT,
        client_name TEXT NOT NULL,
        client_email TEXT,
        rating INTEGER NOT NULL,
        comment TEXT,
        created_at TEXT,
        FOREIGN KEY(master_id) REFERENCES masters(id),
        FOREIGN KEY(booking_id) REFERENCES bookings(id)
    )''')
    
    # Новая таблица для финансов
    c.execute('''CREATE TABLE IF NOT EXISTS transactions (
        id TEXT PRIMARY KEY,
        master_id TEXT NOT NULL,
        type TEXT NOT NULL,
        amount REAL NOT NULL,
        description TEXT,
        booking_id TEXT,
        created_at TEXT,
        FOREIGN KEY(master_id) REFERENCES masters(id)
    )''')
    
    # Таблица для реферральной системы
    c.execute('''CREATE TABLE IF NOT EXISTS referrals (
        id TEXT PRIMARY KEY,
        referrer_id TEXT NOT NULL,
        referee_id TEXT NOT NULL,
        status TEXT DEFAULT 'pending',
        reward_months INTEGER DEFAULT 1,
        created_at TEXT,
        completed_at TEXT,
        FOREIGN KEY(referrer_id) REFERENCES masters(id),
        FOREIGN KEY(referee_id) REFERENCES masters(id)
    )''')
    
    # Таблица для акций/скидок
    c.execute('''CREATE TABLE IF NOT EXISTS discounts (
        id TEXT PRIMARY KEY,
        master_id TEXT NOT NULL,
        title TEXT NOT NULL,
        description TEXT,
        percent INTEGER,
        fixed_amount REAL,
        code TEXT,
        active INTEGER DEFAULT 1,
        max_uses INTEGER,
        used_count INTEGER DEFAULT 0,
        expires_at TEXT,
        created_at TEXT,
        FOREIGN KEY(master_id) REFERENCES masters(id)
    )''')
    
    # Таблица для напоминаний
    c.execute('''CREATE TABLE IF NOT EXISTS reminders (
        id TEXT PRIMARY KEY,
        master_id TEXT NOT NULL,
        booking_id TEXT,
        type TEXT DEFAULT 'booking',
        scheduled_at TEXT,
        sent INTEGER DEFAULT 0,
        message TEXT,
        created_at TEXT,
        FOREIGN KEY(master_id) REFERENCES masters(id),
        FOREIGN KEY(booking_id) REFERENCES bookings(id)
    )''')
    
    # Таблица для логов email
    c.execute('''CREATE TABLE IF NOT EXISTS email_log (
        id TEXT PRIMARY KEY,
        master_id TEXT NOT NULL,
        template_key TEXT,
        sent_at TEXT,
        FOREIGN KEY(master_id) REFERENCES masters(id)
    )''')
    
    db.commit()
    db.close()

def get_db():
    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    return db

@app.teardown_appcontext
def close_db(error):
    db = g.pop('db', None)
    if db is not None:
        db.close()

def get_current_master():
    if 'master_id' not in session:
        return None
    db = get_db()
    row = db.execute('SELECT * FROM masters WHERE id=?', [session['master_id']]).fetchone()
    return dict(row) if row else None

def subscription_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        master = get_current_master()
        if not master:
            return redirect(url_for('login'))
        now = datetime.now()
        try:
            trial_end = datetime.fromisoformat((master['trial_ends_at'] or master['created_at']).replace('Z', ''))
        except:
            trial_end = datetime.fromisoformat(master['created_at'].replace('Z', ''))
        if master['subscription_status'] == 'expired' and now > trial_end:
            return redirect(url_for('subscription_expired'))
        return f(*args, **kwargs)
    return decorated_function

# ── ROUTES ────────────────────────────────────────────────────────────
@app.route('/')
def index():
    master = get_current_master()
    if master:
        return redirect(url_for('dashboard'))
    return redirect(url_for('landing'))

@app.route('/landing')
def landing():
    return render_template('landing.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        
        if not username or not password or not name:
            flash('Заполните все поля', 'error')
            return redirect(url_for('register'))
        
        db = get_db()
        if db.execute('SELECT 1 FROM masters WHERE username=?', [username]).fetchone():
            flash('Пользователь с таким логином уже существует', 'error')
            return redirect(url_for('register'))
        
        master_id = str(uuid.uuid4())
        referral_code = str(uuid.uuid4())[:8].upper()
        now = datetime.now()
        trial_ends = now + timedelta(days=TRIAL_DAYS)
        
        db.execute('''INSERT INTO masters 
            (id, username, password_hash, name, email, created_at, 
             trial_started_at, trial_ends_at, subscription_status, referral_code)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            [master_id, username, generate_password_hash(password), name, email,
             now.isoformat(), now.isoformat(), trial_ends.isoformat(), 'trial', referral_code])
        
        db.commit()
        flash('Аккаунт создан! Войдите в кабинет', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        
        if not username or not password:
            flash('Заполните логин и пароль', 'error')
            return redirect(url_for('login'))
        
        db = get_db()
        row = db.execute('SELECT * FROM masters WHERE username=?', [username]).fetchone()
        
        if not row or not check_password_hash(row['password_hash'], password):
            flash('Неверный логин или пароль', 'error')
            return redirect(url_for('login'))
        
        session['master_id'] = row['id']
        return redirect(url_for('dashboard'))
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('landing'))

@app.route('/subscription-expired')
def subscription_expired():
    return render_template('subscription_expired.html')

@app.route('/dashboard')
@subscription_required
def dashboard():
    master = get_current_master()
    db = get_db()
    
    # Получение заказов на текущей неделе
    today = datetime.now().date()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)
    
    bookings = db.execute('''
        SELECT * FROM bookings 
        WHERE master_id=? AND date >= ? AND date <= ?
        ORDER BY date, time
    ''', [master['id'], str(week_start), str(week_end)]).fetchall()
    
    # Статистика
    total_bookings = len(bookings)
    completed = db.execute('SELECT COUNT(*) as cnt FROM bookings WHERE master_id=? AND status=?',
                          [master['id'], 'completed']).fetchone()['cnt']
    
    # Финансы за текущий месяц
    month_start = today.replace(day=1)
    if month_start.month == 12:
        month_end = month_start.replace(year=month_start.year+1, month=1, day=1) - timedelta(days=1)
    else:
        month_end = month_start.replace(month=month_start.month+1, day=1) - timedelta(days=1)
    
    revenue = db.execute('''
        SELECT SUM(amount) as total FROM transactions 
        WHERE master_id=? AND type='income' AND created_at >= ? AND created_at <= ?
    ''', [master['id'], month_start.isoformat(), month_end.isoformat()]).fetchone()
    
    monthly_income = revenue['total'] if revenue['total'] else 0
    
    return render_template('dashboard.html',
        master=master,
        bookings=bookings,
        total_bookings=total_bookings,
        completed=completed,
        monthly_income=monthly_income)

# ── API: BOOKINGS ────────────────────────────────────────────────────
@app.route('/api/bookings', methods=['GET'])
@subscription_required
def list_bookings():
    master = get_current_master()
    db = get_db()
    rows = db.execute(
        'SELECT * FROM bookings WHERE master_id=? ORDER BY date DESC, time DESC',
        [master['id']]).fetchall()
    return jsonify({'ok': True, 'bookings': [dict(r) for r in rows]})

@app.route('/api/bookings', methods=['POST'])
@subscription_required
def create_booking():
    master = get_current_master()
    data = request.get_json(silent=True) or {}
    
    client_name = str(data.get('client_name', '')).strip()
    client_phone = str(data.get('client_phone', '')).strip()
    client_email = str(data.get('client_email', '')).strip()
    service_id = str(data.get('service_id', '')).strip()
    date = str(data.get('date', '')).strip()
    time = str(data.get('time', '')).strip()
    notes = str(data.get('notes', '')).strip()
    
    if not all([client_name, client_phone, date, time]):
        return jsonify({'ok': False, 'error': 'Заполните все обязательные поля'}), 400
    
    db = get_db()
    bid = str(uuid.uuid4())
    
    db.execute('''INSERT INTO bookings 
        (id, master_id, client_name, client_phone, client_email, service_id, date, time, notes, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
        [bid, master['id'], client_name, client_phone, client_email, service_id, date, time, notes, 'pending', datetime.now().isoformat()])
    
    # Регистрация клиента
    phone_key = re.sub(r'\D', '', client_phone)[-10:]
    existing = db.execute('SELECT id FROM clients WHERE master_id=? AND phone_key=?',
                         [master['id'], phone_key]).fetchone()
    
    if not existing:
        db.execute('''INSERT INTO clients 
            (id, master_id, name, phone, email, phone_key, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)''',
            [str(uuid.uuid4()), master['id'], client_name, client_phone, client_email, phone_key, datetime.now().isoformat()])
    
    db.commit()
    return jsonify({'ok': True, 'id': bid})

@app.route('/api/bookings/<bid>', methods=['PATCH'])
@subscription_required
def update_booking(bid):
    master = get_current_master()
    data = request.get_json(silent=True) or {}
    status = str(data.get('status', '')).strip()
    
    db = get_db()
    row = db.execute('SELECT * FROM bookings WHERE id=? AND master_id=?', [bid, master['id']]).fetchone()
    
    if not row:
        return jsonify({'ok': False, 'error': 'Не найдено'}), 404
    
    if status in ['pending', 'confirmed', 'completed', 'cancelled']:
        db.execute('UPDATE bookings SET status=? WHERE id=?', [status, bid])
        
        # Если заказ завершен, добавить транзакцию
        if status == 'completed':
            service_id = dict(row)['service_id']
            if service_id:
                services = json.loads(master['services'] or '[]')
                service = next((s for s in services if s['id'] == service_id), None)
                if service:
                    amount = float(service.get('price', 0))
                    db.execute('''INSERT INTO transactions 
                        (id, master_id, type, amount, description, booking_id, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)''',
                        [str(uuid.uuid4()), master['id'], 'income', amount, 
                         f"Заказ {dict(row)['client_name']}", bid, datetime.now().isoformat()])
        
        db.commit()
        return jsonify({'ok': True})
    
    return jsonify({'ok': False, 'error': 'Неверный статус'}), 400

@app.route('/api/bookings/<bid>', methods=['DELETE'])
@subscription_required
def delete_booking(bid):
    master = get_current_master()
    db = get_db()
    row = db.execute('SELECT id FROM bookings WHERE id=? AND master_id=?', [bid, master['id']]).fetchone()
    
    if not row:
        return jsonify({'ok': False, 'error': 'Не найдено'}), 404
    
    db.execute('DELETE FROM bookings WHERE id=?', [bid])
    db.commit()
    return jsonify({'ok': True})

# ── API: REVIEWS ─────────────────────────────────────────────────────
@app.route('/api/reviews', methods=['GET'])
@subscription_required
def list_reviews():
    master = get_current_master()
    db = get_db()
    rows = db.execute(
        'SELECT * FROM reviews WHERE master_id=? ORDER BY created_at DESC',
        [master['id']]).fetchall()
    
    reviews = [dict(r) for r in rows]
    avg_rating = 0
    if reviews:
        avg_rating = sum(r['rating'] for r in reviews) / len(reviews)
    
    return jsonify({'ok': True, 'reviews': reviews, 'average_rating': round(avg_rating, 1)})

@app.route('/api/reviews', methods=['POST'])
def create_review():
    """Создание отзыва клиентом (без авторизации)"""
    data = request.get_json(silent=True) or {}
    
    master_id = str(data.get('master_id', '')).strip()
    booking_id = str(data.get('booking_id', '')).strip()
    client_name = str(data.get('client_name', '')).strip()
    client_email = str(data.get('client_email', '')).strip()
    rating = int(data.get('rating', 5))
    comment = str(data.get('comment', '')).strip()
    
    if not all([master_id, client_name, rating]):
        return jsonify({'ok': False, 'error': 'Заполните все поля'}), 400
    
    if not 1 <= rating <= 5:
        return jsonify({'ok': False, 'error': 'Рейтинг должен быть от 1 до 5'}), 400
    
    db = get_db()
    rid = str(uuid.uuid4())
    
    db.execute('''INSERT INTO reviews 
        (id, master_id, booking_id, client_name, client_email, rating, comment, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
        [rid, master_id, booking_id if booking_id else None, client_name, client_email, rating, comment, datetime.now().isoformat()])
    
    # Обновление среднего рейтинга мастера
    avg = db.execute('SELECT AVG(rating) as avg FROM reviews WHERE master_id=?', [master_id]).fetchone()
    if avg['avg']:
        db.execute('UPDATE masters SET rating=? WHERE id=?', [avg['avg'], master_id])
    
    db.commit()
    return jsonify({'ok': True, 'id': rid})

@app.route('/api/reviews/<rid>', methods=['DELETE'])
@subscription_required
def delete_review(rid):
    master = get_current_master()
    db = get_db()
    row = db.execute('SELECT id FROM reviews WHERE id=? AND master_id=?', [rid, master['id']]).fetchone()
    
    if not row:
        return jsonify({'ok': False, 'error': 'Не найдено'}), 404
    
    db.execute('DELETE FROM reviews WHERE id=?', [rid])
    db.commit()
    return jsonify({'ok': True})

# ── API: FINANCES ────────────────────────────────────────────────────
@app.route('/api/finances/summary')
@subscription_required
def finances_summary():
    master = get_current_master()
    db = get_db()
    
    today = datetime.now().date()
    month_start = today.replace(day=1)
    week_start = today - timedelta(days=today.weekday())
    
    # Доходы за месяц
    month_income = db.execute('''
        SELECT SUM(amount) as total FROM transactions 
        WHERE master_id=? AND type='income' AND date(created_at) >= ?
    ''', [master['id'], str(month_start)]).fetchone()['total'] or 0
    
    # Доходы за неделю
    week_income = db.execute('''
        SELECT SUM(amount) as total FROM transactions 
        WHERE master_id=? AND type='income' AND date(created_at) >= ?
    ''', [master['id'], str(week_start)]).fetchone()['total'] or 0
    
    # Расходы за месяц
    expenses = db.execute('''
        SELECT SUM(amount) as total FROM transactions 
        WHERE master_id=? AND type='expense' AND date(created_at) >= ?
    ''', [master['id'], str(month_start)]).fetchone()['total'] or 0
    
    # Чистый доход
    net_income = month_income - expenses
    
    # Доходы по услугам
    income_by_service = db.execute('''
        SELECT SUM(t.amount) as total, b.service_id
        FROM transactions t 
        LEFT JOIN bookings b ON t.booking_id=b.id
        WHERE t.master_id=? AND t.type='income' AND date(t.created_at) >= ?
        GROUP BY b.service_id
    ''', [master['id'], str(month_start)]).fetchall()
    
    services = json.loads(master['services'] or '[]')
    service_names = {s['id']: s['name'] for s in services}
    
    income_data = []
    for row in income_by_service:
        service_id = dict(row)['service_id']
        total = dict(row)['total'] or 0
        service_name = service_names.get(service_id, 'Неизвестная услуга')
        income_data.append({'service': service_name, 'amount': total})
    
    return jsonify({
        'ok': True,
        'month_income': round(month_income, 2),
        'week_income': round(week_income, 2),
        'expenses': round(expenses, 2),
        'net_income': round(net_income, 2),
        'income_by_service': income_data
    })

@app.route('/api/transactions')
@subscription_required
def list_transactions():
    master = get_current_master()
    db = get_db()
    
    rows = db.execute(
        'SELECT * FROM transactions WHERE master_id=? ORDER BY created_at DESC LIMIT 100',
        [master['id']]).fetchall()
    
    return jsonify({'ok': True, 'transactions': [dict(r) for r in rows]})

# ── API: REFERRALS ───────────────────────────────────────────────────
@app.route('/api/referral/info')
@subscription_required
def referral_info():
    master = get_current_master()
    db = get_db()
    
    # Количество успешных рефералов
    referrals = db.execute(
        'SELECT COUNT(*) as cnt FROM referrals WHERE referrer_id=? AND status=?',
        [master['id'], 'completed']).fetchone()['cnt']
    
    # Зарядных месяцев
    reward_months = db.execute(
        'SELECT SUM(reward_months) as total FROM referrals WHERE referrer_id=? AND status=?',
        [master['id'], 'completed']).fetchone()['total'] or 0
    
    return jsonify({
        'ok': True,
        'referral_code': master['referral_code'],
        'referral_link': f"{mail.APP_URL}/register?ref={master['referral_code']}",
        'successful_referrals': referrals,
        'free_months_earned': reward_months,
        'referral_earnings': master['referral_earnings']
    })

# ── API: REMINDERS ───────────────────────────────────────────────────
@app.route('/api/reminders')
@subscription_required
def list_reminders():
    master = get_current_master()
    db = get_db()
    
    rows = db.execute('''
        SELECT r.*, b.client_name, b.client_phone, b.date, b.time
        FROM reminders r 
        LEFT JOIN bookings b ON r.booking_id=b.id
        WHERE r.master_id=? 
        ORDER BY r.scheduled_at DESC
    ''', [master['id']]).fetchall()
    
    return jsonify({'ok': True, 'reminders': [dict(r) for r in rows]})

@app.route('/api/reminders', methods=['POST'])
@subscription_required
def create_reminder():
    master = get_current_master()
    data = request.get_json(silent=True) or {}
    
    booking_id = str(data.get('booking_id', '')).strip()
    scheduled_at = str(data.get('scheduled_at', '')).strip()
    message = str(data.get('message', '')).strip()
    
    if not booking_id or not scheduled_at:
        return jsonify({'ok': False, 'error': 'Укажите запись и время'}), 400
    
    db = get_db()
    row = db.execute('SELECT id FROM bookings WHERE id=? AND master_id=?',
                    [booking_id, master['id']]).fetchone()
    
    if not row:
        return jsonify({'ok': False, 'error': 'Запись не найдена'}), 404
    
    rid = str(uuid.uuid4())
    db.execute('''INSERT INTO reminders 
        (id, master_id, booking_id, scheduled_at, message, created_at)
        VALUES (?, ?, ?, ?, ?, ?)''',
        [rid, master['id'], booking_id, scheduled_at, message, datetime.now().isoformat()])
    
    db.commit()
    return jsonify({'ok': True, 'id': rid})

@app.route('/api/reminders/<rid>', methods=['DELETE'])
@subscription_required
def delete_reminder(rid):
    master = get_current_master()
    db = get_db()
    row = db.execute('SELECT id FROM reminders WHERE id=? AND master_id=?', [rid, master['id']]).fetchone()
    
    if not row:
        return jsonify({'ok': False, 'error': 'Не найдено'}), 404
    
    db.execute('DELETE FROM reminders WHERE id=?', [rid])
    db.commit()
    return jsonify({'ok': True})

# ── API: DISCOUNTS ───────────────────────────────────────────────────
@app.route('/api/discounts')
@subscription_required
def list_discounts():
    master = get_current_master()
    db = get_db()
    
    rows = db.execute(
        'SELECT * FROM discounts WHERE master_id=? ORDER BY created_at DESC',
        [master['id']]).fetchall()
    
    return jsonify({'ok': True, 'discounts': [dict(r) for r in rows]})

@app.route('/api/discounts', methods=['POST'])
@subscription_required
def create_discount():
    master = get_current_master()
    data = request.get_json(silent=True) or {}
    
    title = str(data.get('title', '')).strip()[:120]
    description = str(data.get('description', '')).strip()[:500]
    percent = int(data.get('percent', 0) or 0)
    percent = max(1, min(100, percent))
    code = str(data.get('code', '')).strip()[:20].upper()
    
    if not title:
        return jsonify({'ok': False, 'error': 'Укажите название акции'}), 400
    
    db = get_db()
    did = str(uuid.uuid4())
    
    db.execute('''INSERT INTO discounts 
        (id, master_id, title, description, percent, code, active, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
        [did, master['id'], title, description, percent, code or None, 1, datetime.now().isoformat()])
    
    db.commit()
    return jsonify({'ok': True, 'id': did})

@app.route('/api/discounts/<did>', methods=['PATCH'])
@subscription_required
def toggle_discount(did):
    master = get_current_master()
    db = get_db()
    row = db.execute('SELECT * FROM discounts WHERE id=? AND master_id=?', [did, master['id']]).fetchone()
    
    if not row:
        return jsonify({'ok': False, 'error': 'Не найдено'}), 404
    
    new_active = 0 if dict(row)['active'] else 1
    db.execute('UPDATE discounts SET active=? WHERE id=?', [new_active, did])
    db.commit()
    
    return jsonify({'ok': True, 'active': new_active})

@app.route('/api/discounts/<did>', methods=['DELETE'])
@subscription_required
def delete_discount(did):
    master = get_current_master()
    db = get_db()
    row = db.execute('SELECT id FROM discounts WHERE id=? AND master_id=?', [did, master['id']]).fetchone()
    
    if not row:
        return jsonify({'ok': False, 'error': 'Не найдено'}), 404
    
    db.execute('DELETE FROM discounts WHERE id=?', [did])
    db.commit()
    return jsonify({'ok': True})

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    init_db()
    mail.start_email_worker(app, get_db, interval_sec=3600)
    app.run(debug=True, port=5000)
