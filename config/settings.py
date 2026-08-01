from pathlib import Path
import os
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "unsafe-dev-key")
DEBUG = os.getenv("DJANGO_DEBUG", "0") == "1"

raw_hosts = os.getenv("DJANGO_ALLOWED_HOSTS", "")
ALLOWED_HOSTS = [h.strip() for h in raw_hosts.split(",") if h.strip()]

# Derived straight from ALLOWED_HOSTS so it can't drift out of sync when a
# domain is added/removed — needed for POSTs to work once served over HTTPS
# behind the reverse proxy (was missing entirely before the creaganaweb.es cutover).
CSRF_TRUSTED_ORIGINS = [f"https://{h}" for h in ALLOWED_HOSTS]

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
#    por dominio (HTTP referrers: creaganaweb.es/*) y por API (solo "Maps
#    JavaScript API"). Nunca se usa para llamadas de servidor.
#  - GOOGLE_PLACES_API_KEY: solo se usa desde el servidor (nunca se envía al
#    cliente), para las búsquedas de Places. Debe restringirse por IP del
#    servidor y por API (solo "Places API (New)"). Al no exponerse nunca al
#    navegador, no necesita restricción de dominio.
# Sin estas claves el buscador de lugares y el mapa interno fallan de forma
# explícita (ver prospeccion/places.py) en vez de degradar silenciosamente.
GOOGLE_MAPS_JS_API_KEY = os.getenv('GOOGLE_MAPS_JS_API_KEY', '')
GOOGLE_PLACES_API_KEY = os.getenv('GOOGLE_PLACES_API_KEY', '')
GOOGLE_PLACES_DAILY_QUOTA = int(os.getenv('GOOGLE_PLACES_DAILY_QUOTA', '300'))  # legacy, ver PlacesApiUsage

# Tope mensual DURO por tipo de request/SKU (ver prospeccion/places.py:
# _reserve_call). El mes de facturación se calcula en America/Los_Angeles,
# igual que Google Cloud Billing — no en la hora del servidor. El límite
# gratuito real de Google para cada SKU Enterprise es 1000/mes; se deja un
# margen de seguridad local (900 por defecto) para frenar ANTES de que
# empiece a facturarse, no justo al límite.
GOOGLE_PLACES_NEARBY_ENTERPRISE_MONTHLY_LIMIT = int(os.getenv('GOOGLE_PLACES_NEARBY_ENTERPRISE_MONTHLY_LIMIT', '900'))
GOOGLE_PLACES_TEXT_ENTERPRISE_MONTHLY_LIMIT = int(os.getenv('GOOGLE_PLACES_TEXT_ENTERPRISE_MONTHLY_LIMIT', '900'))
GOOGLE_PLACES_PLACE_DETAILS_ENTERPRISE_MONTHLY_LIMIT = int(
    os.getenv('GOOGLE_PLACES_PLACE_DETAILS_ENTERPRISE_MONTHLY_LIMIT', '900')
)
# Aviso (no bloqueante) si en un solo día se supera este número de llamadas
# — para detectar un uso anómalo antes de que se acumule todo el mes.
GOOGLE_PLACES_DAILY_WARNING_LIMIT = int(os.getenv('GOOGLE_PLACES_DAILY_WARNING_LIMIT', '50'))
# Solo para la estimación de coste ORIENTATIVA que se muestra en el panel —
# nunca sustituye a la factura real de Google Cloud Billing.
GOOGLE_PLACES_ENTERPRISE_PRICE_PER_1000_USD = float(
    os.getenv('GOOGLE_PLACES_ENTERPRISE_PRICE_PER_1000_USD', '35')
)

# Bridge de WhatsApp no oficial compartido con el proyecto `anna` (mismo
# servidor, servicio systemd brimoon-whatsapp-bridge — ver prospeccion/wa_bridge.py).
# Se usa solo para mandar el informe del chequeo digital al WhatsApp del
# propio respondente ("de parte de Tania"), nunca para el chat en vivo del
# sitio (eso sigue siendo core/wa_send.py, la API oficial de Meta).
WHATSAPP_BRIDGE_URL = os.getenv('WHATSAPP_BRIDGE_URL', 'http://127.0.0.1:8125')
WHATSAPP_BRIDGE_TOKEN = os.getenv('WHATSAPP_BRIDGE_TOKEN', '')
WHATSAPP_BRIDGE_SESSION = os.getenv('WHATSAPP_BRIDGE_SESSION', 'aura_demo')

USE_TZ = True

# Email via Brevo SMTP relay (external) / Mailcow (internal fallback)
EMAIL_BACKEND   = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST      = os.getenv('BREVO_HOST', '127.0.0.1')
EMAIL_PORT      = int(os.getenv('BREVO_PORT', 25))
EMAIL_USE_TLS   = bool(os.getenv('BREVO_HOST', ''))
EMAIL_HOST_USER = os.getenv('BREVO_USER', '')
EMAIL_HOST_PASSWORD = os.getenv('BREVO_PASS', '')
DEFAULT_FROM_EMAIL  = 'info@creaganaweb.es'

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {'console': {'class': 'logging.StreamHandler'}},
    'root': {'handlers': ['console'], 'level': 'INFO'},
}
