from django.conf import settings
from django.http import HttpRequest


def settings_flags(request: HttpRequest) -> dict[str, bool]:
    return {
        'ENABLE_USER_MANAGEMENT': getattr(settings, 'ENABLE_USER_MANAGEMENT', False),
    }
