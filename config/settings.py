from pathlib import Path
import os
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "unsafe-dev-key")
DEBUG = os.getenv("DJANGO_DEBUG", "0") == "1"

raw_hosts = os.getenv("DJANGO_ALLOWED_HOSTS", "")
ALLOWED_HOSTS = [h.strip() for h in raw_hosts.split(",") if h.strip()]

INSTALLED_APPS = [
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.staticfiles',
    'core',
    'crm',
    'planner',
    'prospeccion',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

SESSION_ENGINE = 'django.contrib.sessions.backends.db'
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

STATIC_URL = '/static/'
STATICFILES_DIRS = [
    '/home/seradmin/listoya/static/',
]

# Client portal media (project materials uploaded by clients)
# Files served through protected Django view, NOT via Nginx directly.
MEDIA_URL  = '/media/'
MEDIA_ROOT = BASE_DIR.parent / 'media'

# 15 MB upload limit per file (enforced in services.py; Nginx allows 20M)
DATA_UPLOAD_MAX_MEMORY_SIZE  = 16 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE  = 16 * 1024 * 1024

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Calendario BE Success — acceso simple por PIN (no es Django auth completo)
PLANNER_ADMIN_PASSWORD = os.getenv('PLANNER_ADMIN_PASSWORD', '1111')
PLANNER_ADMIN_TOKEN = os.getenv('PLANNER_ADMIN_TOKEN', 'be-admin-9f3ac2d1e7')

# Google Maps — dos claves DISTINTAS con alcance mínimo cada una:
#  - GOOGLE_MAPS_JS_API_KEY: se envía al navegador para dibujar el mapa base
#    en /panel/prospeccion/mapa/. Debe restringirse en Google Cloud Console
#    por dominio (HTTP referrers: webimpulsa.es/*) y por API (solo "Maps
#    JavaScript API"). Nunca se usa para llamadas de servidor.
#  - GOOGLE_PLACES_API_KEY: solo se usa desde el servidor (nunca se envía al
#    cliente), para las búsquedas de Places. Debe restringirse por IP del
#    servidor y por API (solo "Places API (New)"). Al no exponerse nunca al
#    navegador, no necesita restricción de dominio.
# Sin estas claves el buscador de lugares y el mapa interno fallan de forma
# explícita (ver prospeccion/places.py) en vez de degradar silenciosamente.
GOOGLE_MAPS_JS_API_KEY = os.getenv('GOOGLE_MAPS_JS_API_KEY', '')
GOOGLE_PLACES_API_KEY = os.getenv('GOOGLE_PLACES_API_KEY', '')
GOOGLE_PLACES_DAILY_QUOTA = int(os.getenv('GOOGLE_PLACES_DAILY_QUOTA', '300'))

USE_TZ = True

# Email via Brevo SMTP relay (external) / Mailcow (internal fallback)
EMAIL_BACKEND   = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST      = os.getenv('BREVO_HOST', '127.0.0.1')
EMAIL_PORT      = int(os.getenv('BREVO_PORT', 25))
EMAIL_USE_TLS   = bool(os.getenv('BREVO_HOST', ''))
EMAIL_HOST_USER = os.getenv('BREVO_USER', '')
EMAIL_HOST_PASSWORD = os.getenv('BREVO_PASS', '')
DEFAULT_FROM_EMAIL  = 'info@webimpulsa.es'

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {'console': {'class': 'logging.StreamHandler'}},
    'root': {'handlers': ['console'], 'level': 'INFO'},
}
