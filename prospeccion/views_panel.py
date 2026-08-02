import json
import logging
import re
from collections import Counter, defaultdict
from datetime import timedelta

from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from crm.views import _crm_auth

from . import places
from .constants import SALES_STATUS_COLORS
from .csv_import import parse_csv, validate_csv_file
from .messaging_templates import build_opener_variants, build_referral_message
from .models import (
    CONSENT_TEXT_VERSION, BusinessContact, BusinessProspect, ChequeoAudit, PlacesApiLimitNotification,
    PlacesApiMonthlyCounter, PlacesApiRequestLog, ProspectPhoto, SECTOR_CHOICES, StaffMember,
)
from .quiz_config import QUESTIONNAIRE_VERSION, QUESTIONS
from .scoring import compute_score, questions_for_sector
from .services import (
    convert_prospect_to_lead, create_draft_proposal_for_prospect, create_prospect, find_duplicate,
    find_existing_matches, find_nearby_prospects, publication_status,
)

logger = logging.getLogger(__name__)


def _prospect_json(p):
    return {
        'id': p.pk,
        'name': p.name,
        'sector': p.sector,
        'sales_status': p.sales_status,
        'color': SALES_STATUS_COLORS.get(p.sales_status, '#8a94a6'),
        'priority': p.priority,
        'lat': p.lat,
        'lng': p.lng,
        'needs_manual_placement': p.needs_manual_placement,
        'address': p.address,
        'district': p.district,
        'municipality': p.municipality,
        'phone': p.phone,
        'email': p.email,
        'website': p.website,
        'whatsapp': p.whatsapp,
        'gmaps_url': p.gmaps_url,
        'current_score': p.current_score,
        'has_website': p.has_website,
        'has_online_booking': p.has_online_booking,
        'has_whatsapp_cta': p.has_whatsapp_cta,
        'assigned_to_id': p.assigned_to_id,
        'assigned_to_name': p.assigned_to.name if p.assigned_to_id else '',
        'last_check_at': p.last_check_at.isoformat() if p.last_check_at else None,
        'next_action_at': p.next_action_at.isoformat() if p.next_action_at else None,
        'public_token': p.public_token,
        'detail_url': f'/panel/prospeccion/{p.pk}/',
    }


@_crm_auth
def dashboard(request):
    funnel = [
        {
            'id': status_id,
            'label': label,
            'color': SALES_STATUS_COLORS.get(status_id, '#8a94a6'),
            'count': BusinessProspect.objects.filter(sales_status=status_id).count(),
        }
        for status_id, label in BusinessProspect.SALES_STATUS_CHOICES
    ]

    won = BusinessProspect.objects.filter(sales_status=BusinessProspect.SALES_WON).count()
    lost = BusinessProspect.objects.filter(sales_status=BusinessProspect.SALES_LOST).count()
    decided = won + lost
    conversion_rate = round(100 * won / decided) if decided else None

    # nota: sqlite no soporta distinct('campo') (eso es DISTINCT ON de
    # Postgres), así que se busca el último audit confirmado por prospecto
    # con una consulta por prospecto en vez de una única query agregada —
    # aceptable aquí porque este dashboard no es de alto tráfico.
    by_id = {q['id']: q for q in QUESTIONS}
    problem_counter = Counter()
    sector_counter = Counter()
    district_counter = Counter()
    for p in BusinessProspect.objects.exclude(current_score__isnull=True):
        sector_counter[p.sector] += 1
        if p.district:
            district_counter[p.district] += 1
        latest_audit = p.audits.filter(stage=ChequeoAudit.STAGE_CONFIRMADO).order_by('-created_at').first()
        if latest_audit:
            for qid in (latest_audit.fix_ids or []):
                q = by_id.get(qid)
                if q:
                    problem_counter[q['text_by_sector'].get(latest_audit.sector, q['text_by_sector']['_default'])] += 1

    sector_labels = dict(SECTOR_CHOICES)
    top_sectors = [
        {'code': code, 'label': sector_labels.get(code, code), 'count': count}
        for code, count in sector_counter.most_common(5)
    ]

    return render(request, 'prospeccion/dashboard.html', {
        'total': BusinessProspect.objects.count(),
        'funnel': funnel,
        'conversion_rate': conversion_rate,
        'won': won,
        'lost': lost,
        'top_problems': problem_counter.most_common(5),
        'top_sectors': top_sectors,
        'top_districts': district_counter.most_common(5),
    })


@_crm_auth
def internal_map(request):
    from django.conf import settings as dj_settings
    return render(request, 'prospeccion/map_internal.html', {
        'sectors': SECTOR_CHOICES,
        'sales_statuses': BusinessProspect.SALES_STATUS_CHOICES,
        'staff': StaffMember.objects.filter(active=True),
        'status_colors_json': json.dumps(SALES_STATUS_COLORS),
        'google_maps_js_api_key': dj_settings.GOOGLE_MAPS_JS_API_KEY,
    })


@_crm_auth
@require_GET
def prospects_bbox_api(request):
    qs = BusinessProspect.objects.select_related('assigned_to')

    try:
        south = float(request.GET['south'])
        north = float(request.GET['north'])
        west = float(request.GET['west'])
        east = float(request.GET['east'])
        qs = qs.filter(lat__gte=south, lat__lte=north, lng__gte=west, lng__lte=east)
    except (KeyError, ValueError):
        pass  # sin bbox -> se usa para listar "sin ubicar" o para la carga inicial

    sector = request.GET.get('sector')
    if sector:
        qs = qs.filter(sector=sector)
    status = request.GET.get('sales_status')
    if status:
        qs = qs.filter(sales_status=status)
    assigned = request.GET.get('assigned_to')
    if assigned:
        qs = qs.filter(assigned_to_id=assigned)
    min_score = request.GET.get('min_score')
    if min_score:
        try:
            qs = qs.filter(current_score__gte=int(min_score))
        except ValueError:
            pass
    if request.GET.get('has_website') == '1':
        qs = qs.filter(has_website=True)
    if request.GET.get('has_online_booking') == '1':
        qs = qs.filter(has_online_booking=True)
    if request.GET.get('has_whatsapp_cta') == '1':
        qs = qs.filter(has_whatsapp_cta=True)
    if request.GET.get('unresolved') == '1':
        qs = qs.filter(needs_manual_placement=True)
    q = request.GET.get('q')
    if q:
        qs = qs.filter(name__icontains=q)

    qs = qs[:2000]
    return JsonResponse({'prospects': [_prospect_json(p) for p in qs]})


@_crm_auth
@require_POST
def add_prospect(request):
    try:
        payload = json.loads(request.body or '{}')
    except (ValueError, TypeError):
        return JsonResponse({'error': 'JSON inválido'}, status=400)

    name = (payload.get('name') or '').strip()
    if not name:
        return JsonResponse({'error': 'El nombre es obligatorio'}, status=400)

    source = payload.get('source') or (
        BusinessProspect.SOURCE_MAP_CLICK if payload.get('lat') is not None
        else BusinessProspect.SOURCE_MANUAL
    )
    prospect, created = create_prospect(payload, source=source)
    return JsonResponse({'prospect': _prospect_json(prospect), 'created': created})


@_crm_auth
@require_POST
def import_csv_view(request):
    f = request.FILES.get('file')
    if not f:
        return JsonResponse({'error': 'Falta el fichero'}, status=400)
    err = validate_csv_file(f)
    if err:
        return JsonResponse({'error': err}, status=400)

    rows, parse_errors = parse_csv(f)
    created, duplicates, unresolved = 0, 0, 0
    for row in rows:
        prospect, is_new = create_prospect(row, source=BusinessProspect.SOURCE_CSV)
        if is_new:
            created += 1
            if prospect.needs_manual_placement:
                unresolved += 1
        else:
            duplicates += 1

    return JsonResponse({
        'created': created,
        'duplicates': duplicates,
        'unresolved': unresolved,
        'errors': parse_errors,
    })


def _existing_match_json(p):
    # Superconjunto de _prospect_json (mismo contexto autenticado del panel)
    # + 'prospect_id'/'sector_label' para que el resultado de búsqueda pueda
    # pintarse también como marcador en el mapa (lat/lng/color/current_score)
    # y no solo como tarjeta en la lista.
    data = _prospect_json(p)
    data['prospect_id'] = p.pk
    data['sector_label'] = p.get_sector_display()
    return data


def _places_quota_response(exc):
    """Respuesta 429 cuando _reserve_call bloqueó la llamada ANTES de tocar
    Google — forma fija, sin más campos, tal como la consume el frontend."""
    return JsonResponse({
        'ok': False,
        'code': 'google_places_monthly_limit_reached',
        'message': str(exc),
        'request_type': exc.request_type,
        'used': exc.used,
        'limit': exc.limit,
        'billing_month': exc.billing_month,
    }, status=429)


@_crm_auth
@require_GET
def places_search(request):
    """Búsqueda única: primero empresas ya en CreaGanaWeb, después resultados
    de Google Places sesgados a la zona visible del mapa (o España por
    defecto). Cada resultado de Google se anota con el prospect existente
    si ya hay uno (mismo place_id, teléfono, dominio, nombre+coords cercanas)."""
    query = (request.GET.get('q') or '').strip()
    if not query:
        return JsonResponse({'error': 'Falta el texto de búsqueda'}, status=400)

    existing = [_existing_match_json(p) for p in find_existing_matches(query)]

    lat = lng = None
    try:
        lat = float(request.GET['lat'])
        lng = float(request.GET['lng'])
    except (KeyError, ValueError):
        pass

    google_results = []
    google_error = None
    try:
        raw_results = places.search_text(query, lat=lat, lng=lng)
        for r in raw_results:
            dup = None
            if r['lat'] is not None and r['lng'] is not None:
                dup = find_duplicate(
                    r['name'], r['phone'], '', r['website'], r['lat'], r['lng'],
                    google_place_id=r['place_id'],
                )
            r['existing_prospect_id'] = dup.pk if dup else None
            google_results.append(r)
    except places.PlacesQuotaExceeded as e:
        return _places_quota_response(e)
    except places.PlacesConfigError as e:
        google_error = str(e)
    except Exception:
        logger.exception('Error buscando en Google Places: query=%r', query)
        google_error = 'No se pudo consultar Google Places en este momento'

    return JsonResponse({'existing': existing, 'google': google_results, 'google_error': google_error})


# Tope alto para "Buscar en esta zona" (radio calculado desde el viewport
# visible del mapa, puede ser bastante mayor que el 1 km de "Estoy aquí"
# cuando la vista está alejada) — evita gastar cuota en un radio de
# provincia entera si alguien hace zoom out del todo.
_NEARBY_MAX_RADIUS_M = 15000


@_crm_auth
@require_GET
def places_nearby(request):
    """Negocios en un radio alrededor de un punto, sin escribir ningún texto
    (a diferencia de places_search). Lo usan dos botones: "Estoy aquí"
    (geolocalización real, radio fijo de 1 km) y "Buscar en esta zona"
    (centro + radio del viewport visible del mapa). Misma lógica de "ya
    existente vs. nuevo de Google" que la búsqueda por texto."""
    try:
        lat = float(request.GET['lat'])
        lng = float(request.GET['lng'])
    except (KeyError, ValueError):
        return JsonResponse({'error': 'Faltan coordenadas (lat/lng)'}, status=400)

    try:
        radius_requested = int(request.GET.get('radius', 1000))
    except ValueError:
        radius_requested = 1000
    radius_m = min(max(radius_requested, 100), _NEARBY_MAX_RADIUS_M)
    radius_capped = radius_requested > _NEARBY_MAX_RADIUS_M

    existing = [_existing_match_json(p) for p in find_nearby_prospects(lat, lng, radius_m=radius_m)]

    google_results = []
    google_error = None
    try:
        raw_results = places.search_nearby(lat, lng, radius_m=radius_m)
        for r in raw_results:
            dup = None
            if r['lat'] is not None and r['lng'] is not None:
                dup = find_duplicate(
                    r['name'], r['phone'], '', r['website'], r['lat'], r['lng'],
                    google_place_id=r['place_id'],
                )
            r['existing_prospect_id'] = dup.pk if dup else None
            google_results.append(r)
    except places.PlacesQuotaExceeded as e:
        return _places_quota_response(e)
    except places.PlacesConfigError as e:
        google_error = str(e)
    except Exception:
        logger.exception('Error buscando cerca en Google Places: lat=%r lng=%r', lat, lng)
        google_error = 'No se pudo consultar Google Places en este momento'

    return JsonResponse({
        'existing': existing, 'google': google_results, 'google_error': google_error,
        'radius_used': radius_m, 'radius_capped': radius_capped,
    })


@_crm_auth
@require_GET
def place_details_view(request):
    """Ficha de un icono de negocio del mapa BASE de Google (no uno de
    nuestros marcadores) — botón "🔍 Obtener info" del popup que se muestra
    al hacer clic. A diferencia de "Añadir directamente" (que no llama a
    Google en absoluto), esto SÍ gasta una unidad de cuota — solo cuando el
    equipo decide activamente que necesita ver si el negocio ya tiene web
    antes de actuar."""
    place_id = (request.GET.get('place_id') or '').strip()
    if not place_id:
        return JsonResponse({'error': 'Falta place_id'}, status=400)

    try:
        result = places.get_place_details(place_id)
    except places.PlacesQuotaExceeded as e:
        return _places_quota_response(e)
    except places.PlacesConfigError as e:
        return JsonResponse({'error': str(e)})
    except Exception:
        logger.exception('Error obteniendo ficha de Google Places: place_id=%r', place_id)
        return JsonResponse({'error': 'No se pudo consultar Google Places en este momento'})

    dup = None
    if result['lat'] is not None and result['lng'] is not None:
        dup = find_duplicate(
            result['name'], result['phone'], '', result['website'], result['lat'], result['lng'],
            google_place_id=result['place_id'],
        )
    result['existing_prospect_id'] = dup.pk if dup else None
    result['detail_url'] = f'/panel/prospeccion/{dup.pk}/' if dup else None
    return JsonResponse({'place': result})


# Se muestran siempre estas filas en el widget/estadísticas aunque el mes
# todavía no tenga ninguna llamada — son los tres tipos que puede producir
# este CRM (place_details_enterprise, desde el botón "Obtener info" del
# popup de iconos del mapa base).
_PRIMARY_REQUEST_TYPES = ('nearby_search_enterprise', 'text_search_enterprise', 'place_details_enterprise')


def _mode_label(log):
    """Nunca se guarda explícitamente qué botón disparó la búsqueda — se
    infiere para mostrar en el historial sin exponer coordenadas reales:
    texto vs. "cerca de mí" (radio fijo ~1 km) vs. "área del mapa" (radio
    variable, calculado del viewport). Devuelve un CÓDIGO estable, no texto
    humano — la traducción ES/RU la hace el frontend (ver map.mode_* en
    map_internal.html), este endpoint no sabe en qué idioma está el CRM."""
    if log.request_type.startswith('text_search'):
        return 'text'
    if log.radius_m is not None and log.radius_m <= 1200:
        return 'nearby'
    return 'area'


def _usage_snapshot():
    billing_month = places.billing_month_for()
    now = timezone.now()

    counters = {c.request_type: c for c in PlacesApiMonthlyCounter.objects.filter(billing_month=billing_month)}

    by_type = {}
    for request_type in _PRIMARY_REQUEST_TYPES:
        c = counters.get(request_type)
        limit = places.monthly_limit_for(request_type)
        used = c.reserved_count if c else 0
        percent = round((used / limit) * 100, 1) if limit else 0.0
        by_type[request_type] = {
            'used': used,
            'successful': c.success_count if c else 0,
            'errors': c.error_count if c else 0,
            'limit': limit,
            'remaining': max(limit - used, 0),
            'percent': percent,
            'blocked': used >= limit,
        }
    month_total = sum(c.reserved_count for c in counters.values())

    today_local = places.to_billing_tz(now).date()
    # today_total: cuenta por día de facturación (America/Los_Angeles), no
    # por medianoche del servidor — coherente con billing_month.
    today_total = sum(
        1 for log in PlacesApiRequestLog.objects.filter(created_at__gte=now - timedelta(hours=36))
        if places.to_billing_tz(log.created_at).date() == today_local
    )

    last_14 = defaultdict(lambda: defaultdict(int))
    since = now - timedelta(days=14)
    for log in PlacesApiRequestLog.objects.filter(created_at__gte=since).only('created_at', 'request_type'):
        day = places.to_billing_tz(log.created_at).strftime('%Y-%m-%d')
        last_14[day][log.request_type] += 1
    last_14_days = [{'date': d, 'counts': dict(v)} for d, v in sorted(last_14.items())]

    last_log = PlacesApiRequestLog.objects.order_by('-created_at').first()

    warnings = [
        {
            'request_type': n.request_type,
            'threshold': n.threshold,
            'message': (
                f'Casi se alcanza el límite protector de Google Places ({n.request_type}): '
                f'quedan {max(places.monthly_limit_for(n.request_type) - (counters[n.request_type].reserved_count if n.request_type in counters else 0), 0)} peticiones.'
                if n.threshold < 100 else
                f'Peticiones de tipo {n.request_type} detenidas hasta el próximo mes de facturación '
                f'o hasta que un administrador cambie el límite.'
            ),
        }
        for n in PlacesApiLimitNotification.objects.filter(billing_month=billing_month).order_by('threshold')
    ]

    return {
        'billing_month': billing_month,
        'timezone': 'America/Los_Angeles',
        'today_total': today_total,
        'month_total': month_total,
        'by_type': by_type,
        'last_14_days': last_14_days,
        'last_request_at': last_log.created_at.isoformat() if last_log else None,
        'warnings': warnings,
        'price_per_1000_usd': settings.GOOGLE_PLACES_ENTERPRISE_PRICE_PER_1000_USD,
        'estimated_cost_usd': round(
            sum(max(v['used'] - 1000, 0) for v in by_type.values())
            / 1000 * settings.GOOGLE_PLACES_ENTERPRISE_PRICE_PER_1000_USD, 2,
        ),
    }


@_crm_auth
@require_GET
def places_usage_stats(request):
    """Estadística en vivo del gasto en Google Places — auth de CRM, nunca
    expone la clave de API ni credential_id, solo cifras agregadas."""
    return JsonResponse(_usage_snapshot())


@_crm_auth
@require_GET
def places_usage_history(request):
    """Últimas peticiones (reales o bloqueadas) + agregado diario del mes en
    curso. Nunca se muestran coordenadas reales, solo un "modo" inferido
    (ver _mode_label) y el hash ya guardado (no la consulta en crudo)."""
    try:
        limit = min(max(int(request.GET.get('limit', 100)), 1), 500)
    except ValueError:
        limit = 100

    logs = PlacesApiRequestLog.objects.all()[:limit]
    rows = [{
        'created_at': log.created_at.isoformat(),
        'request_type': log.request_type,
        'mode': _mode_label(log),
        'success': log.success,
        'response_status': log.response_status,
        'error_type': log.error_type,
        'result_count': log.result_count,
        'duration_ms': log.duration_ms,
    } for log in logs]

    billing_month = places.billing_month_for()
    daily = defaultdict(lambda: defaultdict(int))
    for log in PlacesApiRequestLog.objects.filter(billing_month=billing_month).only('created_at', 'request_type'):
        day = places.to_billing_tz(log.created_at).strftime('%Y-%m-%d')
        daily[day][log.request_type] += 1
    daily_rows = [{'date': d, 'counts': dict(v)} for d, v in sorted(daily.items())]

    return JsonResponse({'rows': rows, 'daily': daily_rows, 'billing_month': billing_month})


@_crm_auth
@require_POST
def add_prospect_from_place(request):
    """Crea un prospect a partir de un resultado de Google Places que el
    equipo vio y confirmó en el panel (nombre/dirección/coords/categoría/
    teléfono/web ya visibles en la tarjeta de resultado). Solo se guardan
    esos campos + google_place_id/gmaps_url — nunca reviews/fotos/rating/
    horario, que ni siquiera se solicitaron a la API."""
    try:
        payload = json.loads(request.body or '{}')
    except (ValueError, TypeError):
        return JsonResponse({'error': 'JSON inválido'}, status=400)

    name = (payload.get('name') or '').strip()
    if not name:
        return JsonResponse({'error': 'El nombre es obligatorio'}, status=400)

    data = {
        'name': name,
        'sector': payload.get('sector') or 'otro',
        'address': payload.get('address') or '',
        'lat': payload.get('lat'),
        'lng': payload.get('lng'),
        'phone': payload.get('phone') or '',
        'website': payload.get('website') or '',
        'gmaps_url': payload.get('google_maps_url') or '',
        'google_place_id': payload.get('place_id') or '',
    }
    prospect, created = create_prospect(data, source=BusinessProspect.SOURCE_GOOGLE_PLACES)
    return JsonResponse({'prospect': _prospect_json(prospect), 'created': created})


@_crm_auth
@require_POST
def parse_maps_link(request):
    """Resuelve un enlace de Google Maps pegado a mano (incluye enlaces
    acortados maps.app.goo.gl, que necesitan que el SERVIDOR siga la
    redirección — el navegador no puede por CORS) y devuelve lat/lng para
    prellenar el panel de confirmación."""
    try:
        payload = json.loads(request.body or '{}')
    except (ValueError, TypeError):
        return JsonResponse({'error': 'JSON inválido'}, status=400)

    url = payload.get('url') or ''
    result = places.resolve_maps_link(url)
    if not result:
        return JsonResponse({'error': 'No se pudo interpretar ese enlace de Google Maps'}, status=400)
    return JsonResponse(result)


def _prelim_draft_key(pk):
    return f'prelim_draft_{pk}'


def _best_whatsapp_digits(prospect, contacts):
    """Digits-only phone for a wa.me link — prefers the primary contact's
    WhatsApp/phone, falls back to the business-level fields."""
    primary = next((c for c in contacts if c.is_primary), None)
    for candidate in (
        primary.whatsapp if primary else '', primary.phone if primary else '',
        prospect.whatsapp, prospect.phone,
    ):
        digits = re.sub(r'\D', '', candidate or '')
        if digits:
            return digits
    return ''


@_crm_auth
def prospect_detail(request, pk):
    prospect = get_object_or_404(BusinessProspect.objects.select_related('assigned_to', 'converted_client'), pk=pk)
    audits = list(prospect.audits.all()[:20])
    latest_preliminar = next((a for a in audits if a.stage == ChequeoAudit.STAGE_PRELIMINAR), None)
    latest_confirmado = next((a for a in audits if a.stage == ChequeoAudit.STAGE_CONFIRMADO), None)
    is_public, publication_reason = publication_status(prospect)
    contacts = list(prospect.contacts.all())
    is_won = prospect.sales_status == BusinessProspect.SALES_WON
    # Un cliente ya ganado no necesita el mensaje de "toma contacto en frío"
    # (asumiría cosas como "no tenéis web" que ya no son ciertas) — para él
    # solo tiene sentido pedirle una recomendación.
    opener_variants = [] if is_won else build_opener_variants(prospect)

    return render(request, 'prospeccion/prospect_detail.html', {
        'prospect': prospect,
        'contacts': contacts,
        'photos': prospect.site_photos.all(),
        'interactions': prospect.interactions.all()[:50],
        'audits': audits,
        'latest_preliminar': latest_preliminar,
        'latest_confirmado': latest_confirmado,
        'personal_url': request.build_absolute_uri(f'/chequeo-digital/e/{prospect.public_token}/'),
        'staff': StaffMember.objects.filter(active=True),
        'sales_statuses': BusinessProspect.SALES_STATUS_CHOICES,
        'sectors': SECTOR_CHOICES,
        'role_choices': BusinessContact.ROLE_CHOICES,
        'channel_choices': BusinessContact.CHANNEL_CHOICES,
        'is_public': is_public,
        'publication_reason': publication_reason,
        'prelim_draft_json': json.dumps(request.session.get(_prelim_draft_key(pk), {})),
        'status_color': SALES_STATUS_COLORS.get(prospect.sales_status, '#8a94a6'),
        'opener_variants': opener_variants,
        'opener_variants_json': json.dumps(opener_variants),
        'referral_message': build_referral_message(prospect) if is_won else None,
        'whatsapp_digits': _best_whatsapp_digits(prospect, contacts),
    })


@_crm_auth
@require_POST
def convert_to_lead(request, pk):
    prospect = get_object_or_404(BusinessProspect, pk=pk)
    try:
        payload = json.loads(request.body or '{}')
    except (ValueError, TypeError):
        payload = {}
    lead, created = convert_prospect_to_lead(
        prospect,
        contact_name=payload.get('contact_name', ''),
        contact_value=payload.get('contact_value', ''),
    )
    return JsonResponse({
        'created': created,
        'lead_id': lead.pk,
        'lead_url': f'/wi/crm/{lead.pk}/',
    })


@_crm_auth
@require_POST
def draft_proposal(request, pk):
    prospect = get_object_or_404(BusinessProspect, pk=pk)
    if not prospect.converted_client_id:
        lead, _ = convert_prospect_to_lead(prospect)
    try:
        proposal = create_draft_proposal_for_prospect(prospect)
    except ValueError as e:
        return JsonResponse({'error': str(e)}, status=400)
    return JsonResponse({
        'proposal_id': proposal.pk,
        'proposal_url': f'/wi/crm/proposal/{proposal.pk}/',
    })


@_crm_auth
def prospect_qr_png(request, pk):
    import io
    import qrcode

    prospect = get_object_or_404(BusinessProspect, pk=pk)
    url = request.build_absolute_uri(f'/chequeo-digital/e/{prospect.public_token}/')
    img = qrcode.make(url, box_size=10, border=2)
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return HttpResponse(buf.getvalue(), content_type='image/png')


@_crm_auth
def prospect_qr_card(request, pk):
    prospect = get_object_or_404(BusinessProspect, pk=pk)
    return render(request, 'prospeccion/prospect_qr_card.html', {'prospect': prospect})


@_crm_auth
def prospect_pdf(request, pk):
    from .pdf import generate_audit_pdf

    prospect = get_object_or_404(BusinessProspect, pk=pk)
    audit = prospect.audits.order_by('-created_at').first()
    if not audit:
        return HttpResponse('Este prospecto todavía no tiene ningún chequeo.', status=404, content_type='text/plain')

    pdf_bytes = generate_audit_pdf(audit)
    if pdf_bytes is None:
        return HttpResponse('No se pudo generar el PDF.', status=500, content_type='text/plain')

    resp = HttpResponse(pdf_bytes, content_type='application/pdf')
    resp['Content-Disposition'] = f'inline; filename="chequeo-{prospect.pk}.pdf"'
    return resp


@_crm_auth
@require_POST
def prospect_update(request, pk):
    prospect = get_object_or_404(BusinessProspect, pk=pk)
    try:
        payload = json.loads(request.body or '{}')
    except (ValueError, TypeError):
        return JsonResponse({'error': 'JSON inválido'}, status=400)

    allowed_fields = {
        'sales_status', 'priority', 'assigned_to_id', 'staff_notes',
        'lat', 'lng', 'address', 'district', 'municipality', 'needs_manual_placement',
    }
    for field in allowed_fields:
        if field in payload:
            setattr(prospect, field, payload[field])
    if 'lat' in payload and 'lng' in payload and payload['lat'] is not None and payload['lng'] is not None:
        prospect.needs_manual_placement = False
    prospect.save()
    return JsonResponse({'prospect': _prospect_json(prospect)})


@_crm_auth
@require_POST
def prospect_delete(request, pk):
    """Borrado permanente de la ficha de prospección — audits, contactos,
    interacciones y fotos se van con ella (CASCADE). Si ya está convertida en
    cliente, el Lead del CRM no se borra (converted_client es SET_NULL), solo
    se pierde el enlace hacia este historial."""
    prospect = get_object_or_404(BusinessProspect, pk=pk)
    name = prospect.name
    # el CASCADE de Django borra las filas de ProspectPhoto pero no los
    # ficheros en disco — se borran explícitamente primero, mismo patrón que
    # photo_delete().
    for photo in prospect.site_photos.all():
        photo.image.delete(save=False)
    prospect.delete()
    logger.info('Empresa eliminada: prospect #%s (%s)', pk, name)
    return JsonResponse({'deleted': True})


VALID_ANSWER_VALUES = {'si', 'en_parte', 'no_se', 'no', 'no_aplica'}


def _validate_prelim_answers(sector, raw_answers):
    """raw_answers: {qid: {'value':..., 'comment':..., 'evidence_url':...}}."""
    valid_ids = {q['id'] for q in questions_for_sector(sector)}
    clean = {}
    for qid, entry in (raw_answers or {}).items():
        if qid not in valid_ids or not isinstance(entry, dict):
            continue
        value = entry.get('value')
        if value not in VALID_ANSWER_VALUES:
            continue
        clean[qid] = {
            'value': value,
            'comment': str(entry.get('comment') or '')[:500],
            'evidence_url': str(entry.get('evidence_url') or '')[:500],
        }
    return clean


@_crm_auth
@require_POST
def preliminar_save_draft(request, pk):
    prospect = get_object_or_404(BusinessProspect, pk=pk)
    try:
        payload = json.loads(request.body or '{}')
    except (ValueError, TypeError):
        return JsonResponse({'error': 'JSON inválido'}, status=400)

    sector = payload.get('sector') or prospect.sector
    answers = _validate_prelim_answers(sector, payload.get('answers') or {})
    request.session[_prelim_draft_key(pk)] = {'sector': sector, 'answers': answers}
    request.session.modified = True
    return JsonResponse({'saved': True, 'count': len(answers)})


@_crm_auth
@require_POST
def preliminar_complete(request, pk):
    """Calcula con scoring.py y crea un ChequeoAudit NUEVO (stage=preliminar,
    source=public_check por respuesta) — nunca sobreescribe uno anterior."""
    prospect = get_object_or_404(BusinessProspect, pk=pk)
    try:
        payload = json.loads(request.body or '{}')
    except (ValueError, TypeError):
        payload = {}

    draft = request.session.get(_prelim_draft_key(pk), {})
    sector = payload.get('sector') or draft.get('sector') or prospect.sector
    raw_answers = payload.get('answers') or draft.get('answers') or {}
    answers = _validate_prelim_answers(sector, raw_answers)
    if not answers:
        return JsonResponse({'error': 'No hay respuestas válidas que guardar'}, status=400)

    score_input = {qid: entry['value'] for qid, entry in answers.items()}
    result = compute_score(sector, score_input)

    audit = ChequeoAudit.objects.create(
        prospect=prospect,
        mode=ChequeoAudit.MODE_PERSONAL,
        stage=ChequeoAudit.STAGE_PRELIMINAR,
        sector=sector,
        questionnaire_version=QUESTIONNAIRE_VERSION,
        answers=[
            {
                'question_id': qid, 'value': e['value'], 'source': 'public_check',
                'comment': e['comment'], 'evidence_url': e['evidence_url'],
            }
            for qid, e in answers.items()
        ],
        score=result['score'],
        category_scores=result['category_scores'],
        good_ids=result['good_ids'],
        fix_ids=result['fix_ids'],
        sector_benchmark=result['benchmark'],
    )

    prospect.last_check_at = timezone.now()
    if prospect.sales_status == BusinessProspect.SALES_DISCOVERED:
        prospect.sales_status = BusinessProspect.SALES_PRE_AUDITED
    prospect.save(update_fields=['last_check_at', 'sales_status', 'updated_at'])

    request.session.pop(_prelim_draft_key(pk), None)
    logger.info('Auditoría preliminar creada: prospect #%s audit #%s score=%s', pk, audit.pk, audit.score)

    return JsonResponse({
        'audit_id': audit.pk,
        'score': audit.score,
        'stage': audit.stage,
        'created_at': audit.created_at.isoformat(),
    })


_CONTACT_FIELDS = {'name', 'role', 'phone', 'whatsapp', 'email', 'preferred_channel', 'is_primary', 'notes'}


def _contact_json(c):
    return {
        'id': c.pk, 'name': c.name, 'role': c.role, 'role_display': c.get_role_display(),
        'phone': c.phone, 'whatsapp': c.whatsapp, 'email': c.email,
        'preferred_channel': c.preferred_channel, 'is_primary': c.is_primary, 'notes': c.notes,
        'consent_receive_report': c.consent_receive_report,
        'consent_receive_report_at': c.consent_receive_report_at.isoformat() if c.consent_receive_report_at else None,
        'consent_receive_report_method': c.consent_receive_report_method,
        'consent_receive_report_version': c.consent_receive_report_version,
        'consent_receive_report_actor': c.consent_receive_report_actor,
        'consent_receive_report_revoked_at': (
            c.consent_receive_report_revoked_at.isoformat() if c.consent_receive_report_revoked_at else None
        ),
        'consent_commercial_contact': c.consent_commercial_contact,
        'consent_commercial_contact_at': (
            c.consent_commercial_contact_at.isoformat() if c.consent_commercial_contact_at else None
        ),
        'consent_commercial_contact_method': c.consent_commercial_contact_method,
        'consent_commercial_contact_version': c.consent_commercial_contact_version,
        'consent_commercial_contact_actor': c.consent_commercial_contact_actor,
        'consent_commercial_contact_revoked_at': (
            c.consent_commercial_contact_revoked_at.isoformat() if c.consent_commercial_contact_revoked_at else None
        ),
    }


@_crm_auth
@require_POST
def contact_create(request, pk):
    prospect = get_object_or_404(BusinessProspect, pk=pk)
    try:
        payload = json.loads(request.body or '{}')
    except (ValueError, TypeError):
        return JsonResponse({'error': 'JSON inválido'}, status=400)

    contact = BusinessContact(prospect=prospect)
    for field in _CONTACT_FIELDS:
        if field in payload:
            setattr(contact, field, payload[field])
    contact.save()
    logger.info('Contacto creado: prospect #%s contact #%s (%s)', pk, contact.pk, contact.name or '(sin nombre)')
    return JsonResponse({'contact': _contact_json(contact)})


@_crm_auth
@require_POST
def contact_update(request, pk, contact_id):
    contact = get_object_or_404(BusinessContact, pk=contact_id, prospect_id=pk)
    try:
        payload = json.loads(request.body or '{}')
    except (ValueError, TypeError):
        return JsonResponse({'error': 'JSON inválido'}, status=400)

    changed = [f for f in _CONTACT_FIELDS if f in payload and getattr(contact, f) != payload[f]]
    for field in changed:
        setattr(contact, field, payload[field])
    contact.save()
    logger.info('Contacto actualizado: prospect #%s contact #%s campos=%s', pk, contact.pk, changed)
    return JsonResponse({'contact': _contact_json(contact)})


@_crm_auth
@require_POST
def contact_delete(request, pk, contact_id):
    contact = get_object_or_404(BusinessContact, pk=contact_id, prospect_id=pk)
    name = contact.name
    contact.delete()
    logger.info('Contacto eliminado: prospect #%s contact #%s (%s)', pk, contact_id, name or '(sin nombre)')
    return JsonResponse({'deleted': True})


_PHOTO_ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png', 'webp', 'heic', 'heif'}
_PHOTO_MAX_BYTES = 12 * 1024 * 1024  # 12 MB por foto


def _photo_json(photo):
    return {
        'id': photo.pk,
        'url': photo.image.url,
        'caption': photo.caption,
        'uploaded_by': photo.uploaded_by,
        'created_at': photo.created_at.isoformat(),
    }


@_crm_auth
@require_POST
def photo_upload(request, pk):
    prospect = get_object_or_404(BusinessProspect, pk=pk)
    files = request.FILES.getlist('photos')
    if not files:
        return JsonResponse({'error': 'No se ha recibido ninguna foto'}, status=400)

    caption = request.POST.get('caption', '')
    uploaded_by = request.POST.get('uploaded_by', '')
    created = []
    errors = []
    for f in files:
        ext = f.name.rsplit('.', 1)[-1].lower() if '.' in f.name else ''
        if ext not in _PHOTO_ALLOWED_EXTENSIONS:
            errors.append(f'{f.name}: tipo de archivo no permitido (.{ext})')
            continue
        if f.size > _PHOTO_MAX_BYTES:
            errors.append(f'{f.name}: supera el límite de {_PHOTO_MAX_BYTES // 1024 // 1024} MB')
            continue
        photo = ProspectPhoto.objects.create(
            prospect=prospect, image=f, caption=caption, uploaded_by=uploaded_by,
        )
        created.append(_photo_json(photo))

    logger.info('Fotos subidas: prospect #%s creadas=%s errores=%s', pk, len(created), len(errors))
    return JsonResponse({'photos': created, 'errors': errors})


@_crm_auth
@require_POST
def photo_delete(request, pk, photo_id):
    photo = get_object_or_404(ProspectPhoto, pk=photo_id, prospect_id=pk)
    photo.image.delete(save=False)
    photo.delete()
    logger.info('Foto eliminada: prospect #%s photo #%s', pk, photo_id)
    return JsonResponse({'deleted': True})


@_crm_auth
@require_POST
def contact_consent(request, pk, contact_id):
    contact = get_object_or_404(BusinessContact, pk=contact_id, prospect_id=pk)
    try:
        payload = json.loads(request.body or '{}')
    except (ValueError, TypeError):
        return JsonResponse({'error': 'JSON inválido'}, status=400)

    consent_type = payload.get('consent_type')
    action = payload.get('action')
    if consent_type not in ('report', 'commercial') or action not in ('grant', 'revoke'):
        return JsonResponse({'error': 'consent_type/action inválidos'}, status=400)

    now = timezone.now()
    actor = str(payload.get('actor') or '').strip()[:120] or 'sin identificar'
    if consent_type == 'report':
        if action == 'grant':
            contact.consent_receive_report = True
            contact.consent_receive_report_at = now
            contact.consent_receive_report_method = str(payload.get('method') or '')[:50]
            contact.consent_receive_report_version = CONSENT_TEXT_VERSION
            contact.consent_receive_report_actor = actor
            contact.consent_receive_report_revoked_at = None
        else:
            contact.consent_receive_report = False
            contact.consent_receive_report_revoked_at = now
    else:
        if action == 'grant':
            contact.consent_commercial_contact = True
            contact.consent_commercial_contact_at = now
            contact.consent_commercial_contact_method = str(payload.get('method') or '')[:50]
            contact.consent_commercial_contact_version = CONSENT_TEXT_VERSION
            contact.consent_commercial_contact_actor = actor
            contact.consent_commercial_contact_revoked_at = None
        else:
            contact.consent_commercial_contact = False
            contact.consent_commercial_contact_revoked_at = now
    contact.save()
    logger.info('Consentimiento %s %s (actor=%s, version=%s): prospect #%s contact #%s',
                consent_type, action, actor, CONSENT_TEXT_VERSION, pk, contact.pk)
    return JsonResponse({'contact': _contact_json(contact)})


@_crm_auth
@require_POST
def publish_consent_update(request, pk):
    """Override manual del consentimiento de publicación — normalmente lo da
    la propia empresa desde el checkbox al final de su chequeo personal
    (ver personal_publish_consent en views_public.py); esto es solo para
    forzarlo a mano si hace falta. Es la única condición para aparecer en
    /mapa-digital/, no hay una confirmación administrativa aparte."""
    prospect = get_object_or_404(BusinessProspect, pk=pk)
    try:
        payload = json.loads(request.body or '{}')
    except (ValueError, TypeError):
        return JsonResponse({'error': 'JSON inválido'}, status=400)

    action = payload.get('action')
    now = timezone.now()
    if action == 'grant':
        prospect.publish_consent = True
        prospect.publish_consent_at = now
        prospect.publish_revoked_at = None
    elif action == 'revoke':
        prospect.publish_consent = False
        prospect.publish_revoked_at = now
    else:
        return JsonResponse({'error': 'action inválida'}, status=400)
    prospect.save()
    logger.info('Consentimiento de publicación %s: prospect #%s', action, pk)
    is_public, reason = publication_status(prospect)
    return JsonResponse({'is_public': is_public, 'reason': reason})
