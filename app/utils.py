from flask import current_app
from . import db
from .models import Setting, Category, EndingCategory
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from email.message import EmailMessage
import smtplib
import os


def get_setting(key: str, default: str = '') -> str:
    s = Setting.query.filter_by(key=key).first()
    return s.value if s else default


def set_setting(key: str, value: str) -> None:
    s = Setting.query.filter_by(key=key).first()
    if not s:
        s = Setting(key=key, value=value)
        db.session.add(s)
    else:
        s.value = value
    db.session.commit()


def user_management_enabled() -> bool:
    default = '1' if current_app.config.get('ENABLE_USER_MANAGEMENT') else '0'
    return 1

DEFAULT_MIN_STOCK = {
    'sticker': 1000,
    'schal': 20,
    'shirt': 10,
}

DEFAULT_PREFIX_STRING = 'ST-:Sticker:0:1000\nSC-:Schal:0:20\nSH-:Shirt:0:10'


def _get_prefix_definitions() -> dict:
    """Return mapping of SKU prefixes to ``(category, price, min_stock)`` tuples."""
    mapping = {}
    
    # Prefer definitions stored in the Category table
    for cat in Category.query.all():
        if cat.prefix:
            mapping[cat.prefix] = (
                cat.name,
                cat.default_price or 0.0,
                cat.default_min_stock or DEFAULT_MIN_STOCK.get(cat.name.lower(), 0),
            )

    if mapping:
        return mapping

    # Fallback to stored setting (for compatibility / first start)
    raw = get_setting('category_prefixes', DEFAULT_PREFIX_STRING)
    for line in raw.splitlines():
        if ':' not in line:
            continue
        parts = [p.strip() for p in line.split(':')]
        if len(parts) < 2:
            continue
        prefix, category = parts[0], parts[1]
        price = 0.0
        if len(parts) >= 3:
            try:
                price = float(parts[2].replace(',', '.'))
            except ValueError:
                price = 0.0
        min_stock = DEFAULT_MIN_STOCK.get(category.lower(), 0)
        if len(parts) >= 4:
            try:
                min_stock = int(parts[3])
            except ValueError:
                min_stock = DEFAULT_MIN_STOCK.get(category.lower(), 0)
        if prefix and category:
            mapping[prefix] = (category, price, min_stock)
    return mapping

def get_category_prefixes() -> dict:
    """Return mapping of SKU prefixes to category names."""
    return {p: c for p, (c, _, _) in _get_prefix_definitions().items()}



def save_category_prefixes(mapping: dict) -> None:
    """Update Category table from a prefix->category mapping."""
    for prefix, name in mapping.items():
        cat = Category.query.filter_by(name=name).first()
        if not cat:
            cat = Category(name=name)
            db.session.add(cat)
        cat.prefix = prefix
    db.session.commit()


def get_categories() -> list:
    """Return list of all category names from the database."""
    return [c.name for c in Category.query.order_by(Category.name).all()]


def category_from_sku(sku: str) -> str | None:
    """Try to determine category by SKU prefix."""
    for prefix, category in get_category_prefixes().items():
        if sku.startswith(prefix):
            return category
    return None

def price_from_sku(sku: str) -> float | None:
    """Return default price configured for the prefix of *sku*."""
    for prefix, (_, price, _) in _get_prefix_definitions().items():
        if sku.startswith(prefix):
            return price
    return None


def get_default_price(category: str) -> float:
    """Return default price for *category* or ``0.0`` if not defined."""
    for _, (cat, price, _) in _get_prefix_definitions().items():
        if cat == category:
            return price
    return 0.0

def get_default_minimum_stock(category: str) -> int:
    """Return default minimum stock for *category* or ``0`` if not defined."""
    for _, (cat, _, min_stock) in _get_prefix_definitions().items():
        if cat == category:
            return min_stock
    return DEFAULT_MIN_STOCK.get(category.lower(), 0)

def price_from_suffix(sku: str, category: str | None = None) -> float | None:
    """Return unit price configured for a specific combination of category and SKU suffix."""
    for end in EndingCategory.query.all():
        if sku.endswith(end.suffix) and (category is None or end.category == category):
            price = end.price
            multiplier = end.csv_multiplier or 1
            if multiplier and multiplier > 1:
                price = price / multiplier
            return price
    return None


def csv_multiplier_from_suffix(sku: str, category: str | None = None) -> int | None:
    """Return CSV multiplier for a specific combination of category and SKU suffix."""
    for end in EndingCategory.query.all():
        if sku.endswith(end.suffix) and (category is None or end.category == category):
            return end.csv_multiplier or 1
    return None

def generate_reset_token(user_id: int) -> str:
    """Return a signed token for password reset."""
    s = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
    return s.dumps(user_id, salt='password-reset')


def verify_reset_token(token: str, max_age: int = 3600) -> int | None:
    """Return user id if token is valid, else ``None``."""
    s = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
    try:
        return s.loads(token, salt='password-reset', max_age=max_age)
    except (BadSignature, SignatureExpired):
        return None


def send_email(to: str, subject: str, body: str) -> None:
    """Send a plain text email using SMTP settings from the Flask config."""
    server = current_app.config.get('MAIL_SERVER', 'smtp.gmail.com')
    port = int(current_app.config.get('MAIL_PORT', 587))
    username = current_app.config.get('MAIL_USERNAME')
    password = current_app.config.get('MAIL_PASSWORD')
    sender = current_app.config.get('MAIL_SENDER', username)
    use_tls = current_app.config.get('MAIL_USE_TLS', str(port) == '587')
    use_ssl = current_app.config.get('MAIL_USE_SSL', str(port) == '465')

    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = sender or ''
    msg['To'] = to
    msg.set_content(body)

    smtp_class = smtplib.SMTP_SSL if use_ssl else smtplib.SMTP
    with smtp_class(server, port) as smtp:
        if use_tls and not use_ssl:
            smtp.starttls()
        if username and password:
            smtp.login(username, password)
        smtp.send_message(msg)
