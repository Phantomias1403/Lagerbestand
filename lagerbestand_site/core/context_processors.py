from django.conf import settings

def settings_flags(request):
    return {
        'ENABLE_USER_MANAGEMENT': settings.ENABLE_USER_MANAGEMENT,
    }
