"""
Integración con Google Places — SOLO desde el servidor. La clave
GOOGLE_PLACES_API_KEY nunca se envía al navegador (ver views_panel.py /
config/settings.py). Se pide expresamente un field mask mínimo: nunca se
solicitan reviews, fotos, rating ni horario, así que es estructuralmente
imposible que este módulo los guarde — no hay que confiar en que el
resto del código "no los use", ni siquiera se piden a Google.

Control de gasto: cada llamada real (o bloqueada por límite) se reserva y
registra en PlacesApiMonthlyCounter / PlacesApiRequestLog (ver models.py)
ANTES de tocar la red, con un tope mensual duro por tipo de request/SKU —
nunca se llama a Google si el mes ya alcanzó su límite configurado.
"""
import hashlib
import re
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from django.conf import settings
from django.db import transaction
from django.db.models import F

from .models import PlacesApiLimitNotification, PlacesApiMonthlyCounter, PlacesApiRequestLog

TEXT_SEARCH_URL = 'https://places.googleapis.com/v1/places:searchText'
NEARBY_SEARCH_URL = 'https://places.googleapis.com/v1/places:searchNearby'

# Solo lo que el equipo necesita ver y confirmar antes de crear un prospect.
# Nunca reviews, photos, rating, ni regularOpeningHours.
FIELD_MASK = ','.join([
    'places.id',
    'places.displayName',
    'places.formattedAddress',
    'places.location',
    'places.primaryType',
    'places.types',
    'places.nationalPhoneNumber',
    'places.internationalPhoneNumber',
    'places.websiteUri',
    'places.googleMapsUri',
])

REQUEST_TIMEOUT = 8

# Google factura el ciclo mensual de Cloud Billing en este huso horario,
# nunca en el del servidor (Europe/Madrid) ni en UTC — así que el "mes" de
# nuestro control local tiene que calcularse igual, o un mismo día podría
# contarse en el mes equivocado cerca de la medianoche.
_BILLING_TZ = ZoneInfo('America/Los_Angeles')

# Campos de FIELD_MASK que determinan el tier/SKU real que Google factura
# (no lo determina el endpoint por sí solo). Si el mask cambiara a futuro,
# _field_tier() reclasifica automáticamente sin tocar el resto del código.
_CONTACT_FIELDS = {
    'nationalPhoneNumber', 'internationalPhoneNumber', 'websiteUri',
    'regularOpeningHours', 'currentOpeningHours',
}
_ATMOSPHERE_FIELDS = {'rating', 'userRatingCount', 'reviews', 'photos', 'priceLevel'}

_WARNING_THRESHOLDS = (70, 85, 95, 100)

# Mapeo aproximado tipo de Google -> sector propio, solo para prellenar el
# selector (el equipo puede corregirlo antes de guardar).
_TYPE_TO_SECTOR = {
    'restaurant': 'bar', 'bar': 'bar', 'cafe': 'bar', 'meal_takeaway': 'bar',
    'meal_delivery': 'bar', 'night_club': 'bar', 'bakery': 'bar',
    'beauty_salon': 'salon', 'hair_care': 'salon', 'hair_salon': 'salon', 'spa': 'salon', 'nail_salon': 'salon',
    'car_repair': 'taller', 'car_dealer': 'taller', 'car_wash': 'taller',
    'school': 'academia', 'university': 'academia', 'primary_school': 'academia', 'secondary_school': 'academia',
    'doctor': 'clinica', 'physiotherapist': 'clinica', 'dentist': 'clinica', 'hospital': 'clinica',
    'health': 'clinica', 'medical_lab': 'clinica',
    'store': 'tienda', 'clothing_store': 'tienda', 'shoe_store': 'tienda', 'supermarket': 'tienda',
    'grocery_store': 'tienda', 'furniture_store': 'tienda', 'electronics_store': 'tienda',
    'real_estate_agency': 'inmobiliaria',
}


def guess_sector(types):
    for t in types or []:
        sector = _TYPE_TO_SECTOR.get(t)
        if sector:
            return sector
    return 'otro'


class PlacesQuotaExceeded(Exception):
    """Límite mensual (por tipo de request/SKU) alcanzado — no se llegó a
    llamar a Google. Lleva los datos estructurados que necesita la vista
    para construir la respuesta 429."""

    def __init__(self, request_type=None, used=None, limit=None, billing_month=None, message=None):
        self.request_type = request_type
        self.used = used
        self.limit = limit
        self.billing_month = billing_month
        super().__init__(
            message or f'Límite mensual de Google Places alcanzado para {request_type} '
                       f'({used}/{limit} en {billing_month}).'
        )


class PlacesConfigError(Exception):
    pass


def billing_month_for(moment=None):
    """'YYYY-MM' del mes de facturación de Google (America/Los_Angeles).
    Sin argumento usa el instante actual; se acepta un datetime aware para
    poder testear los límites de mes sin depender del reloj real."""
    moment = moment if moment is not None else _now()
    return moment.astimezone(_BILLING_TZ).strftime('%Y-%m')


def to_billing_tz(moment):
    """Convierte un datetime aware a America/Los_Angeles — para agrupar por
    día en el panel de uso con el mismo huso que billing_month_for()."""
    return moment.astimezone(_BILLING_TZ)


def _now():
    from django.utils import timezone
    return timezone.now()


def _field_tier():
    names = {f.split('.', 1)[1] for f in FIELD_MASK.split(',') if '.' in f}
    if names & _ATMOSPHERE_FIELDS:
        return 'enterprise_atmosphere'
    if names & _CONTACT_FIELDS:
        return 'enterprise'
    return 'pro'


def request_type_for(method):
    """method: 'text_search' | 'nearby_search'. Se autoclasifica según qué
    campos pide FIELD_MASK ahora mismo (ver comentario junto a PLACES_
    REQUEST_TYPE_CHOICES en models.py)."""
    tier = _field_tier()
    if tier == 'enterprise_atmosphere':
        # Ninguna de las dos búsquedas de este módulo pide campos de
        # Atmosphere hoy — ese tier de verdad solo existe en el enum para
        # Place Details. Si algún día lo pidieran, se cuentan igual como
        # 'enterprise' antes que perder el aviso por completo.
        tier = 'enterprise'
    return f'{method}_{tier}'


def monthly_limit_for(request_type):
    mapping = {
        'nearby_search_enterprise': settings.GOOGLE_PLACES_NEARBY_ENTERPRISE_MONTHLY_LIMIT,
        'text_search_enterprise': settings.GOOGLE_PLACES_TEXT_ENTERPRISE_MONTHLY_LIMIT,
        'place_details_enterprise': settings.GOOGLE_PLACES_PLACE_DETAILS_ENTERPRISE_MONTHLY_LIMIT,
        'place_details_enterprise_atmosphere': settings.GOOGLE_PLACES_PLACE_DETAILS_ENTERPRISE_MONTHLY_LIMIT,
    }
    return mapping.get(request_type, settings.GOOGLE_PLACES_NEARBY_ENTERPRISE_MONTHLY_LIMIT)


def _hash(value):
    if not value:
        return ''
    return hashlib.sha256(str(value).encode('utf-8')).hexdigest()


def _log_request(*, request_type, billing_month, endpoint, success, response_status=None,
                  error_type='', result_count=None, duration_ms=None, query_hash='',
                  coordinates_hash='', radius_m=None):
    PlacesApiRequestLog.objects.create(
        billing_month=billing_month, request_type=request_type, endpoint=endpoint,
        success=success, response_status=response_status, error_type=(error_type or '')[:120],
        result_count=result_count, duration_ms=duration_ms, query_hash=query_hash,
        coordinates_hash=coordinates_hash, radius_m=radius_m,
    )


def _check_thresholds(request_type, billing_month, used, limit):
    if limit <= 0:
        return
    percent = (used / limit) * 100
    for threshold in _WARNING_THRESHOLDS:
        if percent >= threshold:
            PlacesApiLimitNotification.objects.get_or_create(
                billing_month=billing_month, request_type=request_type, threshold=threshold,
            )


def _reserve_call(request_type):
    """Reserva atómica de una unidad de uso ANTES de llamar a Google. Si el
    mes ya alcanzó el límite configurado para este request_type, registra el
    intento bloqueado y lanza PlacesQuotaExceeded sin tocar la red."""
    billing_month = billing_month_for()
    limit = monthly_limit_for(request_type)

    with transaction.atomic():
        counter, _created = PlacesApiMonthlyCounter.objects.select_for_update().get_or_create(
            billing_month=billing_month, request_type=request_type,
        )
        blocked = counter.reserved_count >= limit
        if not blocked:
            counter.reserved_count = F('reserved_count') + 1
            counter.save(update_fields=['reserved_count'])
            counter.refresh_from_db()

    if blocked:
        _log_request(request_type=request_type, billing_month=billing_month, endpoint='',
                      success=False, error_type='monthly_limit_reached')
        raise PlacesQuotaExceeded(
            request_type=request_type, used=counter.reserved_count, limit=limit, billing_month=billing_month,
        )

    try:
        # Aviso de umbral (70/85/95/100%) — es un extra informativo, nunca
        # debe impedir una llamada a Google ya aprobada y reservada (que
        # SIEMPRE debe seguir adelante) si este paso fallara por lo que sea.
        _check_thresholds(request_type, billing_month, counter.reserved_count, limit)
    except Exception:
        pass
    return billing_month, counter.reserved_count


def _finalize_call(request_type, billing_month, success):
    field = 'success_count' if success else 'error_count'
    with transaction.atomic():
        counter = PlacesApiMonthlyCounter.objects.select_for_update().get(
            billing_month=billing_month, request_type=request_type,
        )
        setattr(counter, field, F(field) + 1)
        counter.save(update_fields=[field])


def search_text(query, lat=None, lng=None, radius_m=15000):
    """Busca lugares por texto libre (nombre, categoría o dirección), con
    sesgo hacia una zona (viewport visible del mapa) y hacia España. Nunca
    pide reviews/fotos/rating/horario — ver FIELD_MASK."""
    if not settings.GOOGLE_PLACES_API_KEY:
        raise PlacesConfigError('GOOGLE_PLACES_API_KEY no configurado')

    request_type = request_type_for('text_search')
    billing_month, _used = _reserve_call(request_type)

    has_coords = lat is not None and lng is not None
    radius = min(max(radius_m, 500), 50000) if has_coords else None
    coordinates_hash = _hash(f'{lat},{lng}') if has_coords else ''
    query_hash = _hash(query)

    body = {
        'textQuery': query,
        'regionCode': 'ES',
        'languageCode': 'es',
    }
    if has_coords:
        body['locationBias'] = {'circle': {'center': {'latitude': lat, 'longitude': lng}, 'radius': radius}}

    start = time.perf_counter()
    try:
        resp = requests.post(
            TEXT_SEARCH_URL,
            json=body,
            headers={
                'X-Goog-Api-Key': settings.GOOGLE_PLACES_API_KEY,
                'X-Goog-FieldMask': FIELD_MASK,
                'Content-Type': 'application/json',
            },
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        results = _map_places(resp.json())
    except Exception as exc:
        duration_ms = int((time.perf_counter() - start) * 1000)
        status = getattr(getattr(exc, 'response', None), 'status_code', None)
        _finalize_call(request_type, billing_month, success=False)
        _log_request(
            request_type=request_type, billing_month=billing_month, endpoint='places:searchText',
            success=False, response_status=status, error_type=type(exc).__name__, duration_ms=duration_ms,
            query_hash=query_hash, coordinates_hash=coordinates_hash, radius_m=radius,
        )
        raise

    duration_ms = int((time.perf_counter() - start) * 1000)
    _finalize_call(request_type, billing_month, success=True)
    _log_request(
        request_type=request_type, billing_month=billing_month, endpoint='places:searchText',
        success=True, response_status=resp.status_code, result_count=len(results), duration_ms=duration_ms,
        query_hash=query_hash, coordinates_hash=coordinates_hash, radius_m=radius,
    )
    return results


def _map_places(data):
    results = []
    for place in data.get('places', []):
        loc = place.get('location') or {}
        types = place.get('types') or []
        results.append({
            'place_id': place.get('id', ''),
            'name': (place.get('displayName') or {}).get('text', ''),
            'address': place.get('formattedAddress', ''),
            'lat': loc.get('latitude'),
            'lng': loc.get('longitude'),
            'category': guess_sector(types),
            'category_raw': place.get('primaryType', ''),
            'phone': place.get('nationalPhoneNumber') or place.get('internationalPhoneNumber') or '',
            'website': place.get('websiteUri', ''),
            'google_maps_url': place.get('googleMapsUri', ''),
        })
    return results


def search_nearby(lat, lng, radius_m=1000):
    """Negocios alrededor de un punto (la geolocalización real del equipo en
    la calle, o el centro del viewport visible del mapa), sin texto de
    búsqueda. Mismo field mask mínimo que search_text."""
    if not settings.GOOGLE_PLACES_API_KEY:
        raise PlacesConfigError('GOOGLE_PLACES_API_KEY no configurado')

    request_type = request_type_for('nearby_search')
    billing_month, _used = _reserve_call(request_type)

    radius = min(max(radius_m, 100), 50000)
    coordinates_hash = _hash(f'{lat},{lng}')

    body = {
        'regionCode': 'ES',
        'languageCode': 'es',
        'maxResultCount': 20,
        'locationRestriction': {'circle': {'center': {'latitude': lat, 'longitude': lng}, 'radius': radius}},
    }

    start = time.perf_counter()
    try:
        resp = requests.post(
            NEARBY_SEARCH_URL,
            json=body,
            headers={
                'X-Goog-Api-Key': settings.GOOGLE_PLACES_API_KEY,
                'X-Goog-FieldMask': FIELD_MASK,
                'Content-Type': 'application/json',
            },
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        results = _map_places(resp.json())
    except Exception as exc:
        duration_ms = int((time.perf_counter() - start) * 1000)
        status = getattr(getattr(exc, 'response', None), 'status_code', None)
        _finalize_call(request_type, billing_month, success=False)
        _log_request(
            request_type=request_type, billing_month=billing_month, endpoint='places:searchNearby',
            success=False, response_status=status, error_type=type(exc).__name__, duration_ms=duration_ms,
            coordinates_hash=coordinates_hash, radius_m=radius,
        )
        raise

    duration_ms = int((time.perf_counter() - start) * 1000)
    _finalize_call(request_type, billing_month, success=True)
    _log_request(
        request_type=request_type, billing_month=billing_month, endpoint='places:searchNearby',
        success=True, response_status=resp.status_code, result_count=len(results), duration_ms=duration_ms,
        coordinates_hash=coordinates_hash, radius_m=radius,
    )
    return results


_COORD_RE = re.compile(r'@(-?\d+\.\d+),(-?\d+\.\d+)')
_COORD_RE_3D4D = re.compile(r'!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)')
_QUERY_LL_RE = re.compile(r'[?&]q=(-?\d+\.\d+),(-?\d+\.\d+)')
_SHORT_LINK_RE = re.compile(r'https?://(maps\.app\.goo\.gl|goo\.gl)/\S+', re.I)


def resolve_maps_link(url):
    """Extrae lat/lng (y opcionalmente un nombre) de un enlace de Google Maps
    pegado a mano. Los enlaces acortados (maps.app.goo.gl) requieren seguir
    la redirección desde el servidor — el navegador no puede por CORS. Esto
    NO es una llamada a la API de Places (no usa API key, no está sujeto a
    los límites/SKU de arriba) — solo sigue una redirección HTTP pública."""
    url = (url or '').strip()
    if not url:
        return None

    final_url = url
    if _SHORT_LINK_RE.match(url):
        try:
            resp = requests.get(url, timeout=REQUEST_TIMEOUT, allow_redirects=True)
            final_url = resp.url
        except requests.RequestException:
            return None

    m = _COORD_RE_3D4D.search(final_url) or _COORD_RE.search(final_url) or _QUERY_LL_RE.search(final_url)
    if not m:
        return None

    lat, lng = float(m.group(1)), float(m.group(2))

    name = ''
    name_match = re.search(r'/place/([^/@]+)/', final_url)
    if name_match:
        name = name_match.group(1).replace('+', ' ')
        import urllib.parse
        name = urllib.parse.unquote(name)

    return {'lat': lat, 'lng': lng, 'name': name, 'google_maps_url': final_url}
