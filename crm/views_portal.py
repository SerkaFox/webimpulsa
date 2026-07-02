"""Client portal views for WebImpulsa CRM.

URL scheme (all public — authenticated by magic-link token):
  GET/POST  /p/<token>/                  portal entry + PIN verification + main view
  POST      /p/<token>/upload/           file upload endpoint
  GET       /p/<token>/file/<pk>/        protected file download
  POST      /p/<token>/proposal/accept/  client accepts the proposal
  POST      /p/<token>/message/          client sends a message to the team
"""
import json
import mimetypes
import logging
import os
import urllib.request

from django.http import (
    FileResponse, Http404, HttpResponse, JsonResponse
)
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt

from .models import ClientAccess, CommunicationLog, Lead, ProjectMaterial, Proposal
from .services import (
    CLIENT_NEXT_STEP, CLIENT_STATUS_LABEL,
    accept_proposal, log_communication, proposal_to_template_input,
    record_portal_visit, save_material, validate_portal_token,
)

_WI_TG_TOKEN   = os.getenv('WI_TG_TOKEN', '')
_WI_TG_CHAT_ID = os.getenv('WI_TG_CHAT_ID', '')


def _notify_tg(text: str) -> None:
    if not (_WI_TG_TOKEN and _WI_TG_CHAT_ID):
        return
    try:
        url  = f'https://api.telegram.org/bot{_WI_TG_TOKEN}/sendMessage'
        data = json.dumps({'chat_id': _WI_TG_CHAT_ID, 'text': text,
                           'parse_mode': 'HTML'}).encode()
        req  = urllib.request.Request(url, data=data,
                                      headers={'Content-Type': 'application/json'})
        urllib.request.urlopen(req, timeout=5)
    except Exception as exc:
        logger.warning('Portal TG notify failed: %s', exc)

logger = logging.getLogger(__name__)

_SESSION_PREFIX = 'portal_v'   # portal_v{token[:16]}


def _session_key(token: str) -> str:
    return f'{_SESSION_PREFIX}{token[:16]}'


def _is_pin_verified(request, token: str) -> bool:
    return bool(request.session.get(_session_key(token)))


def _mark_pin_verified(request, token: str) -> None:
    request.session[_session_key(token)] = True
    request.session.set_expiry(86400)  # 24 hours


# ── Portal entry + PIN verification + main portal (unified view) ──────────────

@require_http_methods(['GET', 'POST'])
def portal(request, token):
    """Single entry point for the client portal.

    Steps:
      1. Validate token → show error page if invalid/expired
      2. If PIN required and not yet verified in session:
         - GET  → show PIN entry form
         - POST → verify PIN; on success, set session flag and show portal
      3. Show full portal (project info + material upload)
    """
    access = validate_portal_token(token)

    if access is None:
        # Check if it existed but is expired/inactive
        expired = ClientAccess.objects.filter(token=token).exists()
        return render(request, 'crm/portal.html', {
            'step':    'invalid',
            'expired': expired,
        })

    lead = access.lead

    # ── PIN verification ──────────────────────────────────────────────────────
    needs_pin = access.pin_required and not _is_pin_verified(request, token)

    if needs_pin:
        if request.method == 'POST' and request.POST.get('_action') == 'verify_pin':
            pin = request.POST.get('pin', '').strip()
            if access.check_pin(pin):
                _mark_pin_verified(request, token)
                needs_pin = False
                log_communication(
                    lead=lead,
                    direction=CommunicationLog.DIR_INBOUND,
                    channel=CommunicationLog.CH_PORTAL,
                    content='Cliente verificó acceso con PIN.',
                    status=CommunicationLog.ST_DELIVERED,
                )
            else:
                logger.warning('Wrong PIN attempt: lead #%d token=%s…', lead.pk, token[:8])
                return render(request, 'crm/portal.html', {
                    'step':      'pin',
                    'access':    access,
                    'lead':      lead,
                    'pin_error': True,
                })
        elif request.method == 'GET':
            return render(request, 'crm/portal.html', {
                'step':   'pin',
                'access': access,
                'lead':   lead,
            })

    # ── Full portal ───────────────────────────────────────────────────────────
    record_portal_visit(access)

    # Fetch client-visible proposal (sent, viewed, or accepted)
    proposal = (lead.proposals
                .filter(status__in=[Proposal.ST_SENT, Proposal.ST_VIEWED, Proposal.ST_ACCEPTED])
                .order_by('-created_at')
                .first())

    proposal_json = None
    if proposal:
        if proposal.status == Proposal.ST_SENT:
            proposal.status = Proposal.ST_VIEWED
            proposal.save(update_fields=['status', 'updated_at'])
            log_communication(
                lead=lead,
                direction=CommunicationLog.DIR_INBOUND,
                channel=CommunicationLog.CH_PORTAL,
                content=f'Propuesta {proposal.number} vista por el cliente en el portal.',
                status=CommunicationLog.ST_READ,
            )
        tmpl = proposal_to_template_input(proposal)
        proposal_json = json.dumps({
            'input':      tmpl,
            'scope':      proposal.scope,
            'outOfScope': proposal.out_of_scope,
            'phases':     proposal.phases,
            'conditions': proposal.conditions,
        }, ensure_ascii=False, default=str)

    materials     = lead.materials.all()
    milestones    = lead.milestones.all()
    status_label  = CLIENT_STATUS_LABEL.get(lead.status, lead.status)
    next_step_msg = CLIENT_NEXT_STEP.get(lead.status, '')
    # Last 10 portal messages (inbound from client + outbound from team)
    portal_msgs = (lead.comm_log
                   .filter(channel=CommunicationLog.CH_PORTAL)
                   .exclude(content__startswith='Cliente verificó')
                   .exclude(content__startswith='Propuesta ')
                   .exclude(content__startswith='Enlace de acceso')
                   .order_by('created_at')[:20])

    return render(request, 'crm/portal.html', {
        'step':            'portal',
        'access':          access,
        'lead':            lead,
        'materials':       materials,
        'milestones':      milestones,
        'portal_msgs':     portal_msgs,
        'status_label':    status_label,
        'next_step':       next_step_msg,
        'wants_materials': lead.status in (Lead.ST_ACEPTADO, Lead.ST_EN_TRABAJO),
        'proposal':        proposal,
        'proposal_json':   proposal_json,
        'accepted':        request.GET.get('accepted') == '1',
        'msg_sent':        request.GET.get('msg') == '1',
    })


# ── File upload ───────────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(['POST'])
def portal_upload(request, token):
    """POST /p/<token>/upload/ — accepts multipart file uploads from client portal."""
    access = validate_portal_token(token)
    if access is None:
        return JsonResponse({'ok': False, 'error': 'Token inválido o expirado'}, status=403)

    needs_pin = access.pin_required and not _is_pin_verified(request, token)
    if needs_pin:
        return JsonResponse({'ok': False, 'error': 'PIN no verificado'}, status=403)

    files   = request.FILES.getlist('files')
    notes   = request.POST.get('notes', '')
    uploader = request.POST.get('uploader_name', access.lead.name)

    if not files:
        return JsonResponse({'ok': False, 'error': 'No se recibieron archivos'}, status=400)

    saved  = []
    errors = []

    for f in files:
        result = save_material(
            lead=access.lead,
            uploaded_file=f,
            source=ProjectMaterial.SRC_PORTAL,
            notes=notes,
            uploaded_by=uploader,
        )
        if isinstance(result, str):
            errors.append({'name': f.name, 'error': result})
        else:
            saved.append({
                'id':   result.pk,
                'name': result.original_filename,
                'size': result.size_display,
                'type': result.file_type,
            })

    return JsonResponse({
        'ok':     True,
        'saved':  saved,
        'errors': errors,
    })


# ── Protected file download ───────────────────────────────────────────────────

@require_http_methods(['GET'])
def portal_file(request, token, pk):
    """Serve a ProjectMaterial file — only if token is valid and verified."""
    access = validate_portal_token(token)
    if access is None:
        raise Http404

    needs_pin = access.pin_required and not _is_pin_verified(request, token)
    if needs_pin:
        raise Http404

    material = get_object_or_404(ProjectMaterial, pk=pk, lead=access.lead)

    if not material.file or not os.path.exists(material.file.path):
        raise Http404

    mime_type, _ = mimetypes.guess_type(material.original_filename)
    mime_type = mime_type or 'application/octet-stream'

    response = FileResponse(
        open(material.file.path, 'rb'),
        content_type=mime_type,
        as_attachment=True,
        filename=material.original_filename,
    )
    return response


# ── Client acceptance of proposal ─────────────────────────────────────────────

@csrf_exempt
@require_http_methods(['POST'])
def portal_accept_proposal(request, token):
    """POST /p/<token>/proposal/accept/ — client accepts the active proposal."""
    access = validate_portal_token(token)
    if access is None:
        return HttpResponse('Enlace inválido o expirado.', status=403)

    needs_pin = access.pin_required and not _is_pin_verified(request, token)
    if needs_pin:
        return HttpResponse('PIN no verificado.', status=403)

    lead     = access.lead
    proposal = (lead.proposals
                .filter(status__in=[Proposal.ST_SENT, Proposal.ST_VIEWED])
                .order_by('-created_at')
                .first())
    if proposal is None:
        return HttpResponse('No hay propuesta activa para aceptar.', status=404)

    agree     = request.POST.get('agree', '').strip()
    name      = request.POST.get('accept_name', '').strip()
    nif       = request.POST.get('accept_nif', '').strip()
    address   = request.POST.get('accept_address', '').strip()
    city      = request.POST.get('accept_city', '').strip()
    signature = request.POST.get('accept_signature', '').strip()

    if not agree:
        return HttpResponse('Debes marcar la casilla de aceptación.', status=400)
    if not name:
        return HttpResponse('El nombre es obligatorio.', status=400)

    accept_proposal(proposal, name, nif, signature)

    # Save fiscal address to proposal if provided
    if address or city or nif:
        if address: proposal.client_address = address[:300]
        if city:    proposal.client_city    = city[:100]
        if nif:     proposal.client_nif     = nif[:30]
        proposal.save(update_fields=['client_address', 'client_city', 'client_nif', 'updated_at'])

    logger.info('Proposal %s accepted via portal: lead #%d by %s',
                proposal.number, lead.pk, name)

    _notify_tg(
        f'✅ <b>Propuesta aceptada</b>\n'
        f'Cliente: {name} ({nif or "sin NIF"})\n'
        f'Propuesta: {proposal.number} — {proposal.total_with_iva}€\n'
        f'→ https://webimpulsa.es/wi/crm/{lead.pk}/'
    )

    return redirect(f'/p/{token}/?accepted=1')


# ── Client message ────────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(['POST'])
def portal_send_message(request, token):
    """POST /p/<token>/message/ — client sends a message to the team."""
    access = validate_portal_token(token)
    if access is None:
        return JsonResponse({'ok': False, 'error': 'Token inválido o expirado'}, status=403)

    needs_pin = access.pin_required and not _is_pin_verified(request, token)
    if needs_pin:
        return JsonResponse({'ok': False, 'error': 'PIN no verificado'}, status=403)

    lead = access.lead
    text = (request.POST.get('message') or '').strip()
    if not text:
        return JsonResponse({'ok': False, 'error': 'Mensaje vacío'}, status=400)
    if len(text) > 2000:
        text = text[:2000]

    log_communication(
        lead=lead,
        direction=CommunicationLog.DIR_INBOUND,
        channel=CommunicationLog.CH_PORTAL,
        content=text,
        status=CommunicationLog.ST_DELIVERED,
    )

    _notify_tg(
        f'💬 <b>Mensaje del portal</b> — {lead.name}\n'
        f'Proyecto: {lead.package or "—"}\n\n'
        f'{text}\n\n'
        f'→ https://webimpulsa.es/wi/crm/{lead.pk}/'
    )

    return redirect(f'/p/{token}/?msg=1')
