"""Email: welcome, nurture, trial reminder. Configure via environment variables."""
import os
import uuid
import smtplib
import ssl
import logging
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

log = logging.getLogger('booksaas.email')

TRIAL_DAYS = 14
MONTHLY_PRICE = '$10/month'
SUPPORT_URL = 'https://t.me/bookSaaS'

MAIL_HOST = os.environ.get('MAIL_HOST', '')
MAIL_PORT = int(os.environ.get('MAIL_PORT', '587'))
MAIL_USER = os.environ.get('MAIL_USER', '')
MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD', '')
MAIL_FROM = os.environ.get('MAIL_FROM', MAIL_USER or 'noreply@booksaas.app')
MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', '1') == '1'
APP_URL = os.environ.get('APP_URL', 'http://127.0.0.1:5000').rstrip('/')

# (days_after_signup, template_key) — прогрев к подписке
NURTURE_SCHEDULE = [
    (0, 'welcome'),
    (2, 'nurture_schedule'),
    (5, 'nurture_link'),
    (9, 'nurture_crm'),
]

def mail_configured():
    return bool(MAIL_HOST and MAIL_FROM)

def _html_wrap(body: str) -> str:
    return f'''<!DOCTYPE html><html lang="ru"><head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#09090b;font-family:Inter,Arial,sans-serif;color:#fafafa">
<table width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:32px 16px">
<table width="560" cellpadding="0" cellspacing="0" style="background:#18181b;border-radius:16px;border:1px solid #27272a">
<tr><td style="padding:32px">{body}
<p style="margin:24px 0 0;font-size:12px;color:#71717a">BookSaaS · <a href="{SUPPORT_URL}" style="color:#f59e0b">Поддержка</a></p>
</td></tr></table></td></tr></table></body></html>'''

def _templates(name: str, master: dict) -> tuple[str, str]:
    n = master.get('name', 'Мастер')
    dash = f'{APP_URL}/'
    reg = f'{APP_URL}/register'
    ends = master.get('trial_ends_at', '')[:10]
    subjects = {
        'welcome': ('Добро пожаловать в BookSaaS', f'''
            <h1 style="color:#f59e0b;margin:0 0 16px;font-size:22px">Здравствуйте, {n}!</h1>
            <p style="color:#d4d4d8;line-height:1.6">Вы начали <strong>14 дней бесплатного пробного периода</strong>.
            После него подписка — <strong>{MONTHLY_PRICE}</strong>.</p>
            <p style="color:#d4d4d8;line-height:1.6">Сейчас настройте профиль, услуги и расписание — это займёт около 2 минут.</p>
            <p style="margin:24px 0"><a href="{dash}" style="display:inline-block;background:#f59e0b;color:#09090b;padding:12px 24px;border-radius:10px;font-weight:700;text-decoration:none">Открыть кабинет</a></p>
        '''),
        'nurture_schedule': ('Настройте расписание за 2 минуты', f'''
            <h1 style="color:#fafafa;margin:0 0 12px;font-size:20px">Привет, {n}!</h1>
            <p style="color:#d4d4d8;line-height:1.6">Клиенты записываются только в свободные слоты. Отметьте дни и часы приёма в кабинете — и отправьте личную ссылку в соцсети.</p>
            <p style="margin:20px 0"><a href="{dash}" style="color:#f59e0b;font-weight:600">Перейти в расписание →</a></p>
        '''),
        'nurture_link': ('Поделитесь ссылкой — получите первую запись', f'''
            <h1 style="color:#fafafa;margin:0 0 12px;font-size:20px">{n}, ваша ссылка готова</h1>
            <p style="color:#d4d4d8;line-height:1.6">Разместите её в Instagram bio, Telegram или ВКонтакте. Мастера получают первые онлайн-записи уже в первый день.</p>
            <p style="margin:20px 0"><a href="{dash}" style="color:#f59e0b;font-weight:600">Скопировать ссылку в кабинете →</a></p>
        '''),
        'nurture_crm': ('CRM: возвращайте клиентов чаще', f'''
            <h1 style="color:#fafafa;margin:0 0 12px;font-size:20px">База клиентов в BookSaaS</h1>
            <p style="color:#d4d4d8;line-height:1.6">Привет, {n}! Во вкладке «Клиенты» — история визитов, заметки и теги. Так проще работать с постоянными и не терять контакты.</p>
            <p style="color:#a1a1aa;font-size:14px">Пробный период ещё активен. После 14 дней — {MONTHLY_PRICE}.</p>
            <p style="margin:20px 0"><a href="{dash}" style="color:#f59e0b;font-weight:600">Открыть CRM →</a></p>
        '''),
        'trial_reminder': (f'Завтра заканчивается пробный период — {MONTHLY_PRICE}', f'''
            <h1 style="color:#f59e0b;margin:0 0 12px;font-size:20px">Остался 1 день пробного периода</h1>
            <p style="color:#d4d4d8;line-height:1.6">Здравствуйте, {n}! Завтра ({ends}) заканчивается бесплатный доступ.
            Чтобы продолжить пользоваться записью и CRM, оформите подписку: <strong>{MONTHLY_PRICE}</strong>.</p>
            <p style="color:#d4d4d8;line-height:1.6">Напишите в поддержку — поможем с оплатой и ответим на вопросы.</p>
            <p style="margin:20px 0">
              <a href="{SUPPORT_URL}" style="display:inline-block;background:#f59e0b;color:#09090b;padding:12px 20px;border-radius:10px;font-weight:700;text-decoration:none;margin-right:8px">Оплатить / связаться</a>
              <a href="{dash}" style="color:#f59e0b">Кабинет</a>
            </p>
        '''),
    }
    sub, body = subjects[name]
    return sub, _html_wrap(body)

def send_email(to: str, subject: str, html: str) -> bool:
    if not to or not mail_configured():
        log.warning('Email skipped (no recipient or MAIL_HOST): %s', subject)
        return False
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = MAIL_FROM
        msg['To'] = to
        msg.attach(MIMEText(html, 'html', 'utf-8'))
        if MAIL_USE_TLS:
            ctx = ssl.create_default_context()
            with smtplib.SMTP(MAIL_HOST, MAIL_PORT, timeout=30) as s:
                s.starttls(context=ctx)
                if MAIL_USER:
                    s.login(MAIL_USER, MAIL_PASSWORD)
                s.sendmail(MAIL_FROM, [to], msg.as_string())
        else:
            with smtplib.SMTP(MAIL_HOST, MAIL_PORT, timeout=30) as s:
                if MAIL_USER:
                    s.login(MAIL_USER, MAIL_PASSWORD)
                s.sendmail(MAIL_FROM, [to], msg.as_string())
        log.info('Sent email to %s: %s', to, subject)
        return True
    except Exception as e:
        log.exception('Email failed to %s: %s', to, e)
        return False

def send_template(db, master_id: str, template_key: str, master: dict) -> bool:
    if not master.get('email'):
        return False
    if db.execute(
        'SELECT 1 FROM email_log WHERE master_id=? AND template_key=?',
        [master_id, template_key]
    ).fetchone():
        return False
    subject, html = _templates(template_key, master)
    if not send_email(master['email'], subject, html):
        return False
    db.execute(
        'INSERT INTO email_log (id, master_id, template_key, sent_at) VALUES (?,?,?,?)',
        [str(uuid.uuid4()), master_id, template_key, datetime.now().isoformat()])
    return True

def trial_end_dt(master: dict):
    raw = master.get('trial_ends_at') or master.get('created_at')
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace('Z', ''))
    except ValueError:
        return None

def process_scheduled_emails(get_db_fn):
    """Run nurture + trial reminder for all masters with email."""
    db = get_db_fn()
    rows = db.execute('SELECT * FROM masters WHERE email IS NOT NULL AND email != ""').fetchall()
    now = datetime.now()
    for row in rows:
        m = dict(row)
        mid = m['id']
        started = datetime.fromisoformat((m.get('trial_started_at') or m['created_at']).replace('Z', ''))
        days = (now - started).days
        for day_offset, key in NURTURE_SCHEDULE:
            if days >= day_offset:
                send_template(db, mid, key, m)
        end = trial_end_dt(m)
        if end:
            days_left = (end.date() - now.date()).days
            if days_left == 1:
                send_template(db, mid, 'trial_reminder', m)
            if m.get('subscription_status') == 'trial' and days_left < 0:
                db.execute(
                    "UPDATE masters SET subscription_status='expired' WHERE id=? AND subscription_status='trial'",
                    [mid])
    db.commit()

def start_email_worker(app, get_db_fn, interval_sec=3600):
    import threading
    import time
    def loop():
        time.sleep(10)
        while True:
            try:
                with app.app_context():
                    process_scheduled_emails(get_db_fn)
            except Exception:
                log.exception('Email worker error')
            time.sleep(interval_sec)
    threading.Thread(target=loop, daemon=True, name='email-worker').start()