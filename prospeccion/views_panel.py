import json

from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET, require_POST

from crm.views import _crm_auth

from .constants import SALES_STATUS_COLORS
from .csv_import import parse_csv, validate_csv_file
from .models import BusinessProspect, SECTOR_CHOICES, StaffMember
from .services import create_prospect


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
    return render(request, 'prospeccion/dashboard.html', {
        'total': BusinessProspect.objects.count(),
        'funnel': funnel,
    })


@_crm_auth
def internal_map(request):
    return render(request, 'prospeccion/map_internal.html', {
        'sectors': SECTOR_CHOICES,
        'sales_statuses': BusinessProspect.SALES_STATUS_CHOICES,
        'staff': StaffMember.objects.filter(active=True),
        'status_colors_json': json.dumps(SALES_STATUS_COLORS),
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


@_crm_auth
def prospect_detail(request, pk):
    prospect = get_object_or_404(BusinessProspect.objects.select_related('assigned_to'), pk=pk)
    return render(request, 'prospeccion/prospect_detail.html', {
        'prospect': prospect,
        'contacts': prospect.contacts.all(),
        'interactions': prospect.interactions.all()[:50],
        'audits': prospect.audits.all()[:20],
        'personal_url': request.build_absolute_uri(f'/chequeo-digital/e/{prospect.public_token}/'),
        'staff': StaffMember.objects.filter(active=True),
        'sales_statuses': BusinessProspect.SALES_STATUS_CHOICES,
    })


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
