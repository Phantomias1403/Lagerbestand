"""WSGI config for Lagerbestand project."""
import os
from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "lagerbestand_site.settings")
application = get_wsgi_application()
