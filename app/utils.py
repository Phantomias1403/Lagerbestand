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


def get_category_prefixes() -> dict:
    """Return mapping of SKU prefixes to categories from settings."""
    raw = get_setting(
        'category_prefixes',
        'ST-:Sticker\nSC-:Schal\nSH-:Shirt'
    )
    mapping = {}
    for line in raw.splitlines():
        if ':' not in line:
            continue
        prefix, category = line.split(':', 1)
        prefix = prefix.strip()
        category = category.strip()
        if prefix and category:
            mapping[prefix] = category
    return mapping


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
