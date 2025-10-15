"""Django settings for the Lagerbestand inventory platform."""
from __future__ import annotations

from pathlib import Path
import os
from datetime import timedelta

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'change-me')
DEBUG = os.environ.get('DJANGO_DEBUG', '0') == '1'
ALLOWED_HOSTS: list[str] = os.environ.get('DJANGO_ALLOWED_HOSTS', '*').split(',')

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',
    'core',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'lagerbestand_site.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'lagerbestand_site' / 'core' / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'core.context_processors.settings_flags',
            ],
        },
    },
]

WSGI_APPLICATION = 'lagerbestand_site.wsgi.application'
ASGI_APPLICATION = 'lagerbestand_site.asgi.application'


_DB_ENGINE = os.environ.get('DB_ENGINE', 'django.db.backends.mysql')
if _DB_ENGINE == 'django.db.backends.mysql':
    DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("DB_NAME", "lagerbestand"),
        "USER": os.getenv("DB_USER", "lageruser"),
        "PASSWORD": os.getenv("DB_PASSWORD", "lagerpass"),
        "HOST": os.getenv("DB_HOST", "postgres"),
        "PORT": os.getenv("DB_PORT", "5432"),
    }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': _DB_ENGINE,
            'NAME': os.environ.get('DB_NAME', BASE_DIR / 'db.sqlite3'),
        }
    }

AUTH_USER_MODEL = 'core.User'

LANGUAGE_CODE = 'de-de'
TIME_ZONE = os.environ.get('TZ', 'Europe/Berlin')
USE_I18N = True
USE_L10N = True
USE_TZ = True

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LOGIN_REDIRECT_URL = 'dashboard'
LOGOUT_REDIRECT_URL = 'login'
LOGIN_URL = 'login'

EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
EMAIL_PORT = int(os.environ.get('MAIL_PORT', 587))
EMAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', '1') == '1'
EMAIL_USE_SSL = os.environ.get('MAIL_USE_SSL', '0') == '1'
EMAIL_HOST_USER = os.environ.get('MAIL_USERNAME', '')
EMAIL_HOST_PASSWORD = os.environ.get('MAIL_PASSWORD', '')
DEFAULT_FROM_EMAIL = os.environ.get('MAIL_SENDER', EMAIL_HOST_USER)

SESSION_COOKIE_AGE = int(os.environ.get('SESSION_AGE', timedelta(hours=8).total_seconds()))
CSRF_TRUSTED_ORIGINS = [
    host if host.startswith('http') else f'https://{host}'
    for host in ALLOWED_HOSTS if host and host != '*'
]

ENABLE_USER_MANAGEMENT = os.environ.get('ENABLE_USER_MANAGEMENT', '1') == '1'

PASSWORD_RESET_TIMEOUT = 60 * 60  # 1 hour
