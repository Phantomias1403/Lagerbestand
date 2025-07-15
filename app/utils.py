from flask import current_app
from . import db
from .models import Setting


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
    return get_setting('enable_user_management', default) == '1'

DEFAULT_MIN_STOCK = {
    'sticker': 1000,
    'schal': 20,
    'shirt': 10,
}



def _get_prefix_definitions() -> dict:
    """Return mapping of SKU prefixes to ``(category, price)`` tuples."""
    raw = get_setting(
        'category_prefixes',
        'ST-:Sticker:0:1000\nSC-:Schal:0:20\nSH-:Shirt:0:10'
    )
    mapping = {}
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
            mapping[prefix] = (category, price)
            mapping[prefix] = (category, price, min_stock)
    return mapping

def get_category_prefixes() -> dict:
    """Return mapping of SKU prefixes to ``(category, price, min_stock)`` tuples."""
    return {p: c for p, (c, _, _) in _get_prefix_definitions().items()}



def save_category_prefixes(mapping: dict) -> None:
    lines = [f"{p}:{c}" for p, c in mapping.items()]
    set_setting('category_prefixes', '\n'.join(lines))


def get_categories() -> list:
    """Return list of all category names."""
    return sorted(set(get_category_prefixes().values()))


def category_from_sku(sku: str) -> str | None:
    """Try to determine category by SKU prefix."""
    for prefix, category in get_category_prefixes().items():
        if sku.startswith(prefix):
            return category
    return None

def price_from_sku(sku: str) -> float | None:
    """Return default price configured for the prefix of *sku*."""
    for _, (cat, price, _) in _get_prefix_definitions().items():
        if sku.startswith(prefix):
            return price
    return None


def get_default_price(category: str) -> float:
    """Return default price for *category* or ``0.0`` if not defined."""
    for _, (cat, price) in _get_prefix_definitions().items():
        if cat == category:
            return price
    return 0.0

def get_default_minimum_stock(category: str) -> int:
    """Return default minimum stock for *category* or ``0`` if not defined."""
    for _, (cat, _, min_stock) in _get_prefix_definitions().items():
        if cat == category:
            return min_stock
    return DEFAULT_MIN_STOCK.get(category.lower(), 0)
