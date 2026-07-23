"""
Integración con Google Places — SOLO desde el servidor. La clave
GOOGLE_PLACES_API_KEY nunca se envía al navegador (ver views_panel.py /
config/settings.py). Se pide expresamente un field mask mínimo: nunca se
solicitan reviews, fotos, rating ni horario, así que es estructuralmente
imposible que este módulo los guarde — no hay que confiar en que el
resto del código "no los use", ni siquiera se piden a Google.
"""
import re
import time

import requests
from django.conf import settings

from .models import PlacesApiUsage

TEXT_SEARCH_URL = 'https://places.googleapis.com/v1/places:searchText'

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
    pass


class PlacesConfigError(Exception):
    pass


def _check_and_increment_quota():
    """Cuota diaria persistida en BD (no hay cache compartida entre workers
    gunicorn). Falla cerrado: si se supera la cuota, no se llama a Google."""
    today = time.strftime('%Y-%m-%d')
    from datetime import date
    row, _ = PlacesApiUsage.objects.get_or_create(date=date.today())
    if row.count >= settings.GOOGLE_PLACES_DAILY_QUOTA:
        raise PlacesQuotaExceeded(
            f'Cuota diaria de búsquedas de Google Places alcanzada ({settings.GOOGLE_PLACES_DAILY_QUOTA}).'
        )
    row.count = row.count + 1
    row.save(update_fields=['count'])


def search_text(query, lat=None, lng=None, radius_m=15000):
    """Busca lugares por texto libre (nombre, categoría o dirección), con
    sesgo hacia una zona (viewport visible del mapa) y hacia España. Nunca
    pide reviews/fotos/rating/horario — ver FIELD_MASK."""
    if not settings.GOOGLE_PLACES_API_KEY:
        raise PlacesConfigError('GOOGLE_PLACES_API_KEY no configurado')

    _check_and_increment_quota()

    body = {
        'textQuery': query,
        'regionCode': 'ES',
        'languageCode': 'es',
    }
    if lat is not None and lng is not None:
        body['locationBias'] = {
            'circle': {
                'center': {'latitude': lat, 'longitude': lng},
                'radius': min(max(radius_m, 500), 50000),
            }
        }

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
    data = resp.json()

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


_COORD_RE = re.compile(r'@(-?\d+\.\d+),(-?\d+\.\d+)')
_COORD_RE_3D4D = re.compile(r'!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)')
_QUERY_LL_RE = re.compile(r'[?&]q=(-?\d+\.\d+),(-?\d+\.\d+)')
_SHORT_LINK_RE = re.compile(r'https?://(maps\.app\.goo\.gl|goo\.gl)/\S+', re.I)


def resolve_maps_link(url):
    """Extrae lat/lng (y opcionalmente un nombre) de un enlace de Google Maps
    pegado a mano. Los enlaces acortados (maps.app.goo.gl) requieren seguir
    la redirección desde el servidor — el navegador no puede por CORS."""
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
