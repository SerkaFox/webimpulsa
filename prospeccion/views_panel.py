import json
import logging
import os
from collections import Counter

from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from crm.views import _crm_auth

from . import places
from .constants import SALES_STATUS_COLORS
from .csv_import import parse_csv, validate_csv_file
from .models import (
    CONSENT_TEXT_VERSION, BusinessContact, BusinessProspect, ChequeoAudit, SECTOR_CHOICES, StaffMember,
)
from .quiz_config import QUESTIONNAIRE_VERSION, QUESTIONS
from .scoring import compute_score, questions_for_sector
from .services import (
    convert_prospect_to_lead, create_draft_proposal_for_prospect, create_prospect, find_duplicate,
    find_existing_matches, publication_status,
)

logger = logging.getLogger(__name__)

# Secreto APARTE de WI_CRM_PASSWORD, solo para confirmar publicaciones. Es
# necesario porque _crm_auth es una única sesión compartida por todo el
# equipo (no hay login individual en este proyecto) — así que elegir un
# StaffMember en un <select> NO demuestra quién está realmente al otro lado
# de la petición; cualquiera con la contraseña general del CRM podría, si no
# fuera por este secreto adicional, enviar el ID de un StaffMember con
# can_confirm_publication=True y confirmar en su nombre. Este secreto reduce
# quién puede hacerlo a quien además lo conozca (compartido solo con las
# personas realmente autorizadas), no a "quien esté logueado en el CRM".
_PUBLISH_CONFIRM_SECRET = os.getenv('WI_PUBLISH_CONFIRM_SECRET', '')


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
        sector_counter[p.get_sector_display()] += 1
        if p.district:
            district_counter[p.district] += 1
        latest_audit = p.audits.filter(stage=ChequeoAudit.STAGE_CONFIRMADO).order_by('-created_at').first()
        if latest_audit:
            for qid in (latest_audit.fix_ids or []):
                q = by_id.get(qid)
                if q:
                    problem_counter[q['text_by_sector'].get(latest_audit.sector, q['text_by_sector']['_default'])] += 1

    return render(request, 'prospeccion/dashboard.html', {
        'total': BusinessProspect.objects.count(),
        'funnel': funnel,
        'conversion_rate': conversion_rate,
        'won': won,
        'lost': lost,
        'top_problems': problem_counter.most_common(5),
        'top_sectors': sector_counter.most_common(5),
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
    return {
        'prospect_id': p.pk,
        'name': p.name,
        'address': p.address,
        'sector': p.sector,
        'sector_label': p.get_sector_display(),
        'detail_url': f'/panel/prospeccion/{p.pk}/',
    }


@_crm_auth
@require_GET
def places_search(request):
    """Búsqueda única: primero empresas ya en WebImpulsa, después resultados
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
    except places.PlacesConfigError as e:
        google_error = str(e)
    except places.PlacesQuotaExceeded as e:
        google_error = str(e)
    except Exception:
        logger.exception('Error buscando en Google Places: query=%r', query)
        google_error = 'No se pudo consultar Google Places en este momento'

    return JsonResponse({'existing': existing, 'google': google_results, 'google_error': google_error})


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


@_crm_auth
def prospect_detail(request, pk):
    prospect = get_object_or_404(BusinessProspect.objects.select_related('assigned_to', 'converted_client'), pk=pk)
    audits = list(prospect.audits.all()[:20])
    latest_preliminar = next((a for a in audits if a.stage == ChequeoAudit.STAGE_PRELIMINAR), None)
    latest_confirmado = next((a for a in audits if a.stage == ChequeoAudit.STAGE_CONFIRMADO), None)
    is_public, publication_reason = publication_status(prospect)

    return render(request, 'prospeccion/prospect_detail.html', {
        'prospect': prospect,
        'contacts': prospect.contacts.all(),
        'interactions': prospect.interactions.all()[:50],
        'audits': audits,
        'latest_preliminar': latest_preliminar,
        'latest_confirmado': latest_confirmado,
        'personal_url': request.build_absolute_uri(f'/chequeo-digital/e/{prospect.public_token}/'),
        'staff': StaffMember.objects.filter(active=True),
        'confirming_staff': StaffMember.objects.filter(active=True, can_confirm_publication=True),
        'sales_statuses': BusinessProspect.SALES_STATUS_CHOICES,
        'sectors': SECTOR_CHOICES,
        'role_choices': BusinessContact.ROLE_CHOICES,
        'channel_choices': BusinessContact.CHANNEL_CHOICES,
        'is_public': is_public,
        'publication_reason': publication_reason,
        'prelim_draft_json': json.dumps(request.session.get(_prelim_draft_key(pk), {})),
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
    """Consentimiento de PUBLICACIÓN dado por la propia empresa — cualquier
    miembro del equipo puede registrarlo, pero por sí solo NO hace nada
    visible: hace falta además publish_confirmed_by_staff (ver publish_confirm)."""
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
        prospect.publish_confirmed_by_staff = False
        prospect.publish_revoked_at = now
    else:
        return JsonResponse({'error': 'action inválida'}, status=400)
    prospect.save()
    logger.info('Consentimiento de publicación %s: prospect #%s', action, pk)
    is_public, reason = publication_status(prospect)
    return JsonResponse({'is_public': is_public, 'reason': reason})


@_crm_auth
@require_POST
def publish_confirm(request, pk):
    """Confirmación ADMINISTRATIVA de publicación — la única acción de todo
    este módulo que exige un StaffMember concreto con can_confirm_publication=
    True. No hay login individual en el proyecto, así que quien confirma se
    indica explícitamente en el momento de la acción y se valida en servidor;
    un miembro de equipo sin ese permiso no puede auto-confirmarse."""
    if not _PUBLISH_CONFIRM_SECRET:
        # fail-closed: sin secreto configurado, nadie puede confirmar (nunca
        # se permite por defecto), igual que _crm_auth falla si falta
        # WI_CRM_PASSWORD.
        return JsonResponse({'error': 'WI_PUBLISH_CONFIRM_SECRET no configurado'}, status=500)

    prospect = get_object_or_404(BusinessProspect, pk=pk)
    try:
        payload = json.loads(request.body or '{}')
    except (ValueError, TypeError):
        return JsonResponse({'error': 'JSON inválido'}, status=400)

    # El staff_member_id elegido en el <select> es solo una ETIQUETA para el
    # registro (quién dice ser) — la sesión CRM es compartida por todo el
    # equipo, así que por sí sola esa elección no prueba identidad. El
    # secreto es lo único que de verdad limita quién puede ejecutar esto.
    provided_secret = payload.get('confirm_secret') or ''
    if not provided_secret or provided_secret != _PUBLISH_CONFIRM_SECRET:
        logger.warning(
            'Intento de confirmar publicación con secreto incorrecto/ausente: prospect #%s staff_id=%s',
            pk, payload.get('staff_member_id'),
        )
        return JsonResponse({'error': 'Secreto de confirmación incorrecto'}, status=403)

    staff = StaffMember.objects.filter(pk=payload.get('staff_member_id'), active=True).first()
    if not staff or not staff.can_confirm_publication:
        logger.warning(
            'Intento de confirmar publicación sin autorización: prospect #%s staff_id=%s',
            pk, payload.get('staff_member_id'),
        )
        return JsonResponse(
            {'error': 'Este miembro del equipo no está autorizado a confirmar publicaciones'}, status=403,
        )

    confirm = bool(payload.get('confirm', True))
    prospect.publish_confirmed_by_staff = confirm
    prospect.save(update_fields=['publish_confirmed_by_staff', 'updated_at'])
    logger.info(
        'Publicación %s por %s (secreto verificado): prospect #%s',
        'confirmada' if confirm else 'desconfirmada', staff.name, pk,
    )
    is_public, reason = publication_status(prospect)
    return JsonResponse({'is_public': is_public, 'reason': reason})
