import base64
import functools
import json
import logging
import os

from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .models import Lead
from .services import lead_from_payload

logger = logging.getLogger(__name__)

_CRM_PASSWORD = os.getenv('WI_CRM_PASSWORD', '')

STATUS_CSS = {
    Lead.ST_NUEVO:       '#2563eb',
    Lead.ST_CONTACTADO:  '#0891b2',
    Lead.ST_PROPUESTA:   '#7c3aed',
    Lead.ST_NEGOCIACION: '#d97706',
    Lead.ST_ACEPTADO:    '#16a34a',
    Lead.ST_EN_TRABAJO:  '#15803d',
    Lead.ST_FINALIZADO:  '#6b7280',
    Lead.ST_PERDIDO:     '#dc2626',
}


def _crm_auth(view):
    @functools.wraps(view)
    def wrapper(request, *args, **kwargs):
        if not _CRM_PASSWORD:
            return HttpResponse('WI_CRM_PASSWORD not configured', status=500,
                                content_type='text/plain')
        auth = request.META.get('HTTP_AUTHORIZATION', '')
        if auth.startswith('Basic '):
            try:
                creds = base64.b64decode(auth[6:]).decode('utf-8')
                _, _, pw = creds.partition(':')
                if pw == _CRM_PASSWORD:
                    return view(request, *args, **kwargs)
            except Exception:
                pass
        resp = HttpResponse('Unauthorized', status=401, content_type='text/plain')
        resp['WWW-Authenticate'] = 'Basic realm="WebImpulsa CRM"'
        return resp
    return wrapper


# ── public API ────────────────────────────────────────────────────────────────

@csrf_exempt
@require_POST
def create_lead(request):
    """POST /wi/crm/leads/ — create a lead from the price calculator."""
    try:
        payload = json.loads(request.body or b'{}')
        if not (payload.get('name') or '').strip():
            return JsonResponse({'ok': False, 'error': 'name required'}, status=400)
        if not (payload.get('contact') or '').strip():
            return JsonResponse({'ok': False, 'error': 'contact required'}, status=400)

        lead = lead_from_payload(payload)
        logger.info('CRM: new lead #%d — %s (%s, %d€)',
                    lead.pk, lead.name, lead.package, lead.estimated_price)
        return JsonResponse({'ok': True, 'lead_id': lead.pk})

    except Exception as e:
        logger.exception('create_lead: %s', e)
        return JsonResponse({'ok': False, 'error': str(e)}, status=500)


# ── admin panel ───────────────────────────────────────────────────────────────

@_crm_auth
def leads_list(request):
    status_filter = request.GET.get('status', '')
    search = request.GET.get('q', '').strip()

    qs = Lead.objects.all()
    if status_filter:
        qs = qs.filter(status=status_filter)
    if search:
        from django.db.models import Q
        qs = qs.filter(
            Q(name__icontains=search) |
            Q(email__icontains=search) |
            Q(phone__icontains=search) |
            Q(biz_type__icontains=search)
        )

    return render(request, 'crm/leads_list.html', {
        'leads':         qs,
        'status_filter': status_filter,
        'search':        search,
        'statuses':      Lead.STATUS_CHOICES,
        'status_css':    STATUS_CSS,
        'total':         qs.count(),
    })


@_crm_auth
def lead_detail(request, pk):
    lead = get_object_or_404(Lead, pk=pk)

    if request.method == 'POST':
        new_status = request.POST.get('status', lead.status)
        new_notes  = request.POST.get('notes', lead.notes)
        if new_status in dict(Lead.STATUS_CHOICES):
            lead.status = new_status
        lead.notes = new_notes
        lead.save(update_fields=['status', 'notes', 'updated_at'])

    return render(request, 'crm/lead_detail.html', {
        'lead':       lead,
        'statuses':   Lead.STATUS_CHOICES,
        'status_css': STATUS_CSS,
    })
