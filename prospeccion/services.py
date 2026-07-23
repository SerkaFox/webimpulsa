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


def _phone_digits(phone):
    digits = re.sub(r'\D', '', phone or '')
    return digits[-9:] if digits else ''


def find_duplicate(name, phone='', email='', website='', lat=None, lng=None, exclude_pk=None):
    """Empresa existente que probablemente sea la misma, o None. Compara de
    forma independiente por teléfono, email, dominio, y nombre+distancia
    corta — un mismo teléfono ya basta para considerarlo duplicado, aunque
    el nombre esté escrito distinto (typo, razón social vs. nombre comercial,
    etc.), en vez de exigir que todo coincida a la vez."""
    from .models import BusinessProspect

    qs = BusinessProspect.objects.all()
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)

    phone_digits = _phone_digits(phone)
    if phone_digits:
        for candidate in qs.exclude(phone=''):
            if _phone_digits(candidate.phone) == phone_digits:
                return candidate

    norm_email = _normalize(email)
    if norm_email:
        match = qs.filter(email__iexact=norm_email).exclude(email='').first()
        if match:
            return match

    domain = _domain_from_url(website)
    if domain:
        for candidate in qs.exclude(website=''):
            if _domain_from_url(candidate.website) == domain:
                return candidate

    norm_name = _normalize(name)
    if norm_name:
        if lat is not None and lng is not None:
            for candidate in qs.filter(lat__isnull=False, lng__isnull=False):
                if _normalize(candidate.name) == norm_name and \
                        _haversine_m(lat, lng, candidate.lat, candidate.lng) <= DEDUPE_DISTANCE_M:
                    return candidate
        # mismo nombre exacto sin coordenadas de por medio — último recurso,
        # más conservador que los anteriores pero evita duplicar lo obvio.
        for candidate in qs:
            if _normalize(candidate.name) == norm_name:
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


# ── Integración con el CRM existente (crm.Lead / crm.Proposal) ────────────────
# Mismos precios base que los botones "calc-project" de tatiana.html — no se
# importan de ahí (son JS), se mantiene esta copia como constante de Python.
PACKAGE_BASE_PRICES = {
    'Landing page': 390,
    'Web profesional': 590,
    'Web con reservas': 890,
    'Tienda online': 1290,
    'Proyecto a medida': 1690,
}

_BOOKING_SECTORS = {'salon', 'bar', 'academia', 'clinica', 'taller', 'inmobiliaria'}


def default_package_for_sector(sector):
    if sector == 'tienda':
        return 'Tienda online'
    if sector in _BOOKING_SECTORS:
        return 'Web con reservas'
    return 'Web profesional'


def _catalog_extra(sector):
    if sector == 'tienda':
        return 'Subir catálogo completo'
    if sector in ('bar', 'academia', 'clinica', 'salon'):
        return 'Menú/catálogo digital'
    return None


def _main_action_extra(sector):
    if sector == 'tienda':
        return 'Pedidos online'
    if sector in _BOOKING_SECTORS:
        return 'Citas y reservas online'
    return None


# question_id (de prospeccion.quiz_config) -> nombre de extra en
# crm.proposal_content.EXTRAS_PRICES, o una función sector -> nombre|None.
# 'mobile_page' y 'reviews_uptodate' no mapean a ningún extra: el primero es
# la base de cualquier paquete, el segundo no tiene SKU equivalente todavía.
FIX_ID_TO_EXTRA = {
    'gbp_accuracy': 'Ficha en Google Maps',
    'catalog_visible': _catalog_extra,
    'one_tap_contact': 'Botón de WhatsApp',
    'main_action_no_wait': _main_action_extra,
    'messages_lost': 'Asistente automático 24h',
    'auto_confirmation': 'Avisos antes de cada cita',
    'centralized_records': 'Panel para tu equipo',
    'repetitive_tasks': 'Documentos automáticos PDF',
    'brings_back_customers': 'Estadísticas de ventas',
}


def extras_from_fix_ids(fix_ids, sector):
    names = []
    for qid in fix_ids:
        entry = FIX_ID_TO_EXTRA.get(qid)
        if entry is None:
            continue
        name = entry(sector) if callable(entry) else entry
        if name and name not in names:
            names.append(name)
    return names


def convert_prospect_to_lead(prospect, contact_name='', contact_value=''):
    """Crea (o reutiliza) un crm.Lead a partir de un BusinessProspect.
    Devuelve (lead, created). Nunca duplica: si ya está convertido, o si ya
    existe un Lead con el mismo teléfono/email, se reutiliza ese."""
    from crm.models import Lead
    from crm.proposal_content import EXTRAS_PRICES
    from crm.services import lead_from_payload

    if prospect.converted_client_id:
        return prospect.converted_client, False

    contact = contact_value or prospect.whatsapp or prospect.phone or prospect.email
    existing = None
    if contact:
        existing = Lead.objects.filter(phone=contact).first() or Lead.objects.filter(email=contact).first()
    if existing:
        prospect.converted_client = existing
        prospect.sales_status = prospect.SALES_CONTACTED
        prospect.save(update_fields=['converted_client', 'sales_status', 'updated_at'])
        return existing, False

    latest_audit = prospect.audits.order_by('-created_at').first()
    fix_ids = latest_audit.fix_ids if latest_audit else []
    package = default_package_for_sector(prospect.sector)
    extras = extras_from_fix_ids(fix_ids, prospect.sector)
    extras_price = sum(EXTRAS_PRICES.get(name, 0) for name in extras)

    payload = {
        'name': contact_name or prospect.name,
        'contact': contact,
        'biz_type': prospect.get_sector_display(),
        'source': Lead.SRC_MAPA_DIGITAL,
        'calc': {
            'package': package,
            'base': PACKAGE_BASE_PRICES.get(package, 590),
            'extras': extras,
            'extras_price': extras_price,
            'rush': False,
            'maint': 0, 'maint_name': '',
            'hours': 0, 'hours_name': '',
            'hosting': 0,
        },
    }
    lead = lead_from_payload(payload)
    prospect.converted_client = lead
    prospect.sales_status = prospect.SALES_CONTACTED
    prospect.save(update_fields=['converted_client', 'sales_status', 'updated_at'])
    return lead, True


def create_draft_proposal_for_prospect(prospect):
    """Crea un borrador de Proposal para el Lead ya convertido. Nunca lo
    envía — igual que crm.services.create_proposal_from_lead, deja el
    borrador en estado ST_DRAFT para que el equipo lo revise antes."""
    from crm.services import create_proposal_from_lead

    if not prospect.converted_client_id:
        raise ValueError('El prospecto todavía no está convertido a cliente')

    proposal = create_proposal_from_lead(prospect.converted_client)
    prospect.sales_status = prospect.SALES_PRESUPUESTO
    prospect.save(update_fields=['sales_status', 'updated_at'])
    return proposal
