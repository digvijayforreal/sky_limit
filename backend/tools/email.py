import re
import smtplib
import sqlite3
import ssl
import uuid
from contextlib import contextmanager
from email.message import EmailMessage
from email.utils import getaddresses
from pathlib import Path
from threading import RLock

PATH = Path(__file__).resolve().parents[2] / 'data' / 'email_settings.db'
LOCK = RLock()
ADDRESS_PATTERN = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')


class EmailToolError(Exception):
    pass


def connect():
    PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(PATH, timeout=15)
    db.row_factory = sqlite3.Row
    db.execute('''CREATE TABLE IF NOT EXISTS email_settings (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        host TEXT NOT NULL,
        port INTEGER NOT NULL,
        username TEXT NOT NULL,
        password TEXT NOT NULL,
        from_email TEXT NOT NULL,
        security TEXT NOT NULL
    )''')
    return db


@contextmanager
def connection():
    db = connect()
    try:
        with db:
            yield db
    finally:
        db.close()


def validate_address(address):
    return bool(ADDRESS_PATTERN.fullmatch(address.strip()))


def save_settings(host, port, username, password, from_email, security):
    host = host.strip()
    username = username.strip()
    from_email = from_email.strip()
    if not host or len(host) > 253 or any(char.isspace() or ord(char) < 32 for char in host):
        raise EmailToolError('Enter a valid SMTP host.')
    if security not in ('starttls', 'ssl'):
        raise EmailToolError('Choose STARTTLS or SSL/TLS security.')
    if not validate_address(from_email):
        raise EmailToolError('Enter a valid sender email address.')
    if username and not password:
        with LOCK, connection() as db:
            saved = db.execute('SELECT username,password FROM email_settings WHERE id=1').fetchone()
            if saved and saved['username']==username:
                password = saved['password']
        if not password:
            raise EmailToolError('Enter the SMTP password for this account.')
    with LOCK, connection() as db:
        db.execute('''INSERT INTO email_settings(id,host,port,username,password,from_email,security)
            VALUES (1,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET host=excluded.host,port=excluded.port,
                username=excluded.username,password=excluded.password,
                from_email=excluded.from_email,security=excluded.security''',
            (host, port, username, password, from_email, security))


def get_settings():
    with LOCK, connection() as db:
        row = db.execute('SELECT * FROM email_settings WHERE id=1').fetchone()
    if not row:
        return {'configured': False, 'has_password': False}
    return {
        'configured': True,
        'host': row['host'],
        'port': row['port'],
        'username': row['username'],
        'from_email': row['from_email'],
        'security': row['security'],
        'has_password': bool(row['password']),
    }


def _load_settings():
    with LOCK, connection() as db:
        row = db.execute('SELECT * FROM email_settings WHERE id=1').fetchone()
    if not row:
        raise EmailToolError('Configure SMTP in Email Settings before sending email.')
    return dict(row)


def clear_settings():
    with LOCK, connection() as db:
        db.execute('DELETE FROM email_settings WHERE id=1')


def validate_email(to, subject, body):
    if not all(isinstance(value, str) for value in (to, subject, body)):
        raise EmailToolError('Email recipient, subject, and body must be text.')
    if any(ord(char) < 32 for char in subject):
        raise EmailToolError('The subject contains invalid control characters.')
    recipients = [address for _, address in getaddresses([to.replace(';', ',')]) if address]
    if not recipients or len(recipients) > 10 or any(not validate_address(address) for address in recipients):
        raise EmailToolError('Provide between 1 and 10 valid recipient email addresses.')
    if not subject.strip() or len(subject) > 250:
        raise EmailToolError('Email subject must be between 1 and 250 characters.')
    if not body.strip() or len(body) > 20000:
        raise EmailToolError('Email body must be between 1 and 20,000 characters.')
    return recipients


def send_email(to, subject, body):
    recipients = validate_email(to, subject, body)
    settings = _load_settings()
    if settings['username'] and not settings['password']:
        raise EmailToolError('SMTP password is missing. Update Email Settings.')
    message = EmailMessage()
    message['From'] = settings['from_email']
    message['To'] = ', '.join(recipients)
    message['Subject'] = subject.strip()
    message.set_content(body)
    context = ssl.create_default_context()
    try:
        if settings['security'] == 'ssl':
            client = smtplib.SMTP_SSL(settings['host'], settings['port'], timeout=30, context=context)
        else:
            client = smtplib.SMTP(settings['host'], settings['port'], timeout=30)
        with client:
            if settings['security'] == 'starttls':
                client.starttls(context=context)
            if settings['username']:
                client.login(settings['username'], settings['password'])
            client.send_message(message)
    except (smtplib.SMTPException, OSError) as exc:
        raise EmailToolError(f'SMTP could not send the email: {exc}') from exc


def create_confirmation(to, subject, body):
    validate_email(to, subject, body)
    confirmation_id = str(uuid.uuid4())
    return confirmation_id
