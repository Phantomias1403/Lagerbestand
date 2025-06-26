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
