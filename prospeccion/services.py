"""
Alta de prospectos con detección de duplicados. Nunca hace scraping masivo
ni copia reseñas/fotos — solo normaliza y compara los datos que el propio
equipo introduce (manual, clic en el mapa o CSV).
"""
import hashlib
import math
import re


def _normalize(s):
    return re.sub(r'\s+', ' ', (s or '').strip().lower())


def _domain_from_url(url):
    if not url:
        return ''
    m = re.search(r'https?://(?:www\.)?([^/]+)', url.strip().lower())
    return m.group(1) if m else ''


def compute_dedupe_key(name, phone='', email='', website=''):
    parts = [_normalize(name)]
    phone_digits = re.sub(r'\D', '', phone or '')
    if phone_digits:
        parts.append(phone_digits[-9:])  # últimos 9 dígitos, sin prefijo de país
    if email:
        parts.append(_normalize(email))
    domain = _domain_from_url(website)
    if domain:
        parts.append(domain)
    key = '|'.join(parts)
    return hashlib.sha256(key.encode('utf-8')).hexdigest()[:32]


def _haversine_m(lat1, lng1, lat2, lng2):
    r = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


DEDUPE_DISTANCE_M = 60


def find_duplicate(name, phone='', email='', website='', lat=None, lng=None, exclude_pk=None):
    """Empresa existente que probablemente sea la misma, o None. Compara por
    nombre+teléfono/email/dominio normalizados, y si hay coordenadas, también
    por nombre igual + distancia corta."""
    from .models import BusinessProspect

    qs = BusinessProspect.objects.all()
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)

    key = compute_dedupe_key(name, phone, email, website)
    exact = qs.filter(dedupe_key=key).first()
    if exact:
        return exact

    if lat is not None and lng is not None:
        norm_name = _normalize(name)
        for candidate in qs.filter(lat__isnull=False, lng__isnull=False):
            if _normalize(candidate.name) != norm_name:
                continue
            if _haversine_m(lat, lng, candidate.lat, candidate.lng) <= DEDUPE_DISTANCE_M:
                return candidate
    return None


def create_prospect(data, source=None):
    """data: dict con al menos 'name'. Devuelve (prospect, created) — si ya
    existe un duplicado, lo devuelve tal cual con created=False, sin tocarlo."""
    from .models import BusinessProspect

    source = source or BusinessProspect.SOURCE_MANUAL
    name = (data.get('name') or '').strip()
    phone = data.get('phone') or ''
    email = data.get('email') or ''
    website = data.get('website') or ''
    lat = data.get('lat')
    lng = data.get('lng')

    dup = find_duplicate(name, phone, email, website, lat, lng)
    if dup:
        return dup, False

    prospect = BusinessProspect.objects.create(
        name=name,
        sector=data.get('sector') or 'otro',
        address=data.get('address') or '',
        district=data.get('district') or '',
        municipality=data.get('municipality') or '',
        lat=lat,
        lng=lng,
        needs_manual_placement=lat is None or lng is None,
        phone=phone,
        email=email,
        website=website,
        whatsapp=data.get('whatsapp') or '',
        gmaps_url=data.get('gmaps_url') or '',
        source=source,
        dedupe_key=compute_dedupe_key(name, phone, email, website),
    )
    return prospect, True
