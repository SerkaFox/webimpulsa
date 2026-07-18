"""Client portal views for WebImpulsa CRM.

URL scheme (all public — authenticated by magic-link token):
  GET/POST  /p/<token>/                  portal entry + PIN verification + main view
  POST      /p/<token>/upload/           file upload endpoint
  GET       /p/<token>/file/<pk>/        protected file download
  POST      /p/<token>/proposal/accept/  client accepts the proposal
  POST      /p/<token>/message/          client sends a message to the team
"""
import hashlib
import json
import mimetypes
import logging
import os
import urllib.request

from django.core.files.base import ContentFile
from django.core.mail import get_connection, EmailMultiAlternatives
from django.http import (
    FileResponse, Http404, HttpResponse, JsonResponse
)
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt

from .models import ClientAccess, CommunicationLog, Lead, ProjectMaterial, Proposal
from .proposal_content import (
    CONDITIONS_BUSINESS, CONDITIONS_CONSUMER, CONSENT_LABELS, WITHDRAWAL_CONSENT_TEXT,
)
from .services import (
    CLIENT_NEXT_STEP, CLIENT_STAGE_PROGRESS, CLIENT_STATUS_LABEL, PAYMENT_PLAN_CHOICES,
    accept_proposal, log_communication, payment_schedule, proposal_to_template_input,
    record_portal_visit, save_material, serialize_chat_message, validate_portal_token,
)

_WI_TG_TOKEN   = os.getenv('WI_TG_TOKEN', '')
_WI_TG_CHAT_ID = os.getenv('WI_TG_CHAT_ID', '')
_OPERATOR_PHONES = [p.strip() for p in os.getenv('WI_OPERATOR_PHONE', '').split(',') if p.strip()]
_BASE_URL = os.getenv('WI_BASE_URL', 'https://webimpulsa.es')

# If Tatiana's admin chat polled within this window, she's "online" for this
# lead — skip duplicate WhatsApp/Telegram pings for new client chat messages.
_ADMIN_ONLINE_WINDOW = 20  # seconds


def _admin_is_online(lead) -> bool:
    seen = lead.admin_chat_seen_at
    return bool(seen and (timezone.now() - seen).total_seconds() < _ADMIN_ONLINE_WINDOW)


def _client_ip(request) -> str:
    """Real client IP behind nginx (X-Forwarded-For), falling back to REMOTE_ADDR."""
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '')


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


def _notify_wa(text: str) -> None:
    """Send plain-text WA notification to all operator phones."""
    if not _OPERATOR_PHONES:
        return
    try:
        from core.wa_send import send_text
        for phone in _OPERATOR_PHONES:
            try:
                send_text(phone, text)
            except Exception as exc:
                logger.warning('Portal WA notify to %s failed: %s', phone, exc)
    except ImportError:
        logger.warning('core.wa_send not available — WA notify skipped')


def _mailcow():
    return get_connection(
        backend='django.core.mail.backends.smtp.EmailBackend',
        host='127.0.0.1', port=25, use_tls=False, username='', password='',
    )


def _brevo():
    return get_connection(
        backend='django.core.mail.backends.smtp.EmailBackend',
        host=os.getenv('BREVO_HOST', 'smtp-relay.brevo.com'),
        port=int(os.getenv('BREVO_PORT', 587)),
        use_tls=True,
        username=os.getenv('BREVO_USER', ''),
        password=os.getenv('BREVO_PASS', ''),
    )


def _send_acceptance_emails(proposal, access, pdf_bytes=None) -> None:
    """Send signed PDF to Tatiana (internal) and to client (with cabinet link)."""
    if pdf_bytes is None:
        from .pdf import generate_proposal_pdf
        pdf_bytes = generate_proposal_pdf(proposal)

    lead       = proposal.lead
    safe_name  = ''.join(c if c.isalnum() or c in '-_' else '_' for c in (lead.name or 'cliente'))
    pdf_name   = f'Propuesta_FIRMADA_{safe_name}_{proposal.number}.pdf'
    cabinet_url = f'{_BASE_URL}/p/{access.token}/'
    signed_at   = (proposal.accepted_at.strftime('%d/%m/%Y %H:%M')
                   if proposal.accepted_at else '—')

    # ── 1. Internal email to Tatiana ─────────────────────────────────────────
    body_int = (
        f'✅ PROPUESTA ACEPTADA\n'
        f'{"─"*38}\n'
        f'Cliente:   {proposal.accepted_by_name or lead.name} ({proposal.get_client_type_display() or "—"})\n'
        f'NIF/CIF:   {proposal.accepted_nif or "—"}\n'
        f'Dirección: {proposal.client_address or "—"}, {proposal.client_postal_code} {proposal.client_city} ({proposal.client_province})\n'
        f'Propuesta: {proposal.number}\n'
        f'Total IVA: {proposal.total_with_iva}€\n'
        f'Firmado:   {signed_at}\n'
        f'Firma:     {proposal.accepted_signature or "—"}\n\n'
        f'→ CRM: https://webimpulsa.es/wi/crm/leads/{lead.pk}/\n'
    )
    try:
        msg_int = EmailMultiAlternatives(
            subject=f'✅ Propuesta aceptada — {lead.name} | {proposal.number}',
            body=body_int,
            from_email='info@webimpulsa.es',
            to=['info@webimpulsa.es'],
            connection=_mailcow(),
        )
        if pdf_bytes:
            msg_int.attach(pdf_name, pdf_bytes, 'application/pdf')
        msg_int.send()
        logger.info('Acceptance internal email sent for proposal %s', proposal.number)
    except Exception as exc:
        logger.error('Acceptance internal email failed %s: %s', proposal.number, exc)

    # ── 2. Confirmation email to client ───────────────────────────────────────
    if not lead.email:
        return

    first = (lead.name.split()[0] if lead.name else 'cliente')
    html_client = f"""<!DOCTYPE html>
<html lang="es">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f0f4f8;font-family:'Segoe UI',Arial,sans-serif">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f0f4f8;padding:28px 12px">
<tr><td align="center">
<table width="560" cellpadding="0" cellspacing="0"
       style="max-width:560px;width:100%;background:#fff;border-radius:10px;
              overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,.07)">

  <!-- Header bar -->
  <tr><td style="padding:20px 32px 16px;border-bottom:3px solid #16a34a">
    <table width="100%" cellpadding="0" cellspacing="0"><tr>
      <td><img src="https://webimpulsa.es/static/wi/img/logo.webp" alt="Web-Impulsa" height="34" style="display:block"></td>
      <td align="right" style="font-size:12px;color:#5a6d8c">
        <span style="background:#f0fdf4;color:#15803d;font-weight:700;padding:4px 10px;border-radius:20px;font-size:11px">
          ✅ Propuesta firmada
        </span>
      </td>
    </tr></table>
  </td></tr>

  <!-- Greeting -->
  <tr><td style="padding:26px 32px 0">
    <p style="font-size:20px;font-weight:800;color:#0c1c42;margin:0 0 8px">¡Gracias, {first}! 🎉</p>
    <p style="font-size:14px;color:#5a6d8c;line-height:1.65;margin:0 0 20px">
      Tu propuesta ha quedado <strong style="color:#15803d">firmada y registrada</strong>.
      Adjunta encontrarás una copia firmada en PDF para tus archivos.
    </p>
  </td></tr>

  <!-- Summary box -->
  <tr><td style="padding:0 32px 20px">
    <table width="100%" cellpadding="0" cellspacing="0"
           style="background:#f5fff8;border-left:4px solid #16a34a;border-radius:0 8px 8px 0;padding:16px 18px">
      <tr><td>
        <p style="font-size:10px;font-weight:700;color:#15803d;text-transform:uppercase;
                  letter-spacing:.08em;margin:0 0 10px">Resumen del acuerdo</p>
        <table width="100%" cellpadding="0" cellspacing="0" style="color:#0c1c42">
          <tr>
            <td style="padding:3px 0;color:#5a6d8c;font-size:13px;width:44%">Proyecto</td>
            <td style="padding:3px 0;font-weight:700;font-size:13px">{proposal.project_name or proposal.package}</td>
          </tr>
          <tr>
            <td style="padding:3px 0;color:#5a6d8c;font-size:13px">Propuesta nº</td>
            <td style="padding:3px 0;font-family:monospace;font-size:12px">{proposal.number}</td>
          </tr>
          <tr>
            <td style="padding:3px 0;color:#5a6d8c;font-size:13px">Total (IVA incl.)</td>
            <td style="padding:3px 0;font-weight:800;font-size:15px;color:#1760d6">{proposal.total_with_iva}€</td>
          </tr>
          <tr>
            <td style="padding:3px 0;color:#5a6d8c;font-size:13px">Firmado por</td>
            <td style="padding:3px 0;font-size:13px">{proposal.accepted_by_name}</td>
          </tr>
          <tr>
            <td style="padding:3px 0;color:#5a6d8c;font-size:13px">Fecha</td>
            <td style="padding:3px 0;font-size:13px">{signed_at}</td>
          </tr>
        </table>
      </td></tr>
    </table>
  </td></tr>

  <!-- CTA cabinet -->
  <tr><td style="padding:0 32px 24px">
    <p style="font-size:14px;color:#5a6d8c;margin:0 0 14px;line-height:1.5">
      Hemos preparado tu <strong style="color:#0c1c42">área de cliente</strong> donde podrás
      ver el progreso del proyecto, enviar archivos (logo, fotos, textos) y escribirnos directamente.
    </p>
    <a href="{cabinet_url}"
       style="display:block;background:#1760d6;color:#fff;text-decoration:none;
              text-align:center;padding:14px 24px;border-radius:8px;
              font-size:15px;font-weight:800;letter-spacing:.01em">
      Entrar a mi área de cliente →
    </a>
    <p style="font-size:11px;color:#94a3b8;text-align:center;margin:8px 0 0">
      Este enlace es personal — guárdalo en tus marcadores
    </p>
  </td></tr>

  <!-- Next steps -->
  <tr><td style="padding:0 32px 24px">
    <p style="font-size:12px;font-weight:700;color:#0c1c42;margin:0 0 8px">¿Qué pasa ahora?</p>
    <table width="100%" cellpadding="0" cellspacing="0">
      <tr><td style="padding:4px 0;font-size:13px;color:#334155">
        <span style="color:#1760d6;font-weight:700">1.</span>&nbsp;
        Te contactamos en menos de 24h para coordinar el inicio
      </td></tr>
      <tr><td style="padding:4px 0;font-size:13px;color:#334155">
        <span style="color:#1760d6;font-weight:700">2.</span>&nbsp;
        Pago del 50% inicial para arrancar el proyecto
      </td></tr>
      <tr><td style="padding:4px 0;font-size:13px;color:#334155">
        <span style="color:#1760d6;font-weight:700">3.</span>&nbsp;
        ¡Empezamos! Seguimiento en tu área de cliente
      </td></tr>
    </table>
  </td></tr>

  <!-- Footer -->
  <tr><td style="padding:16px 32px;background:#f8fafc;border-top:1px solid #e2e8f0">
    <table width="100%" cellpadding="0" cellspacing="0"><tr>
      <td>
        <p style="margin:0 0 2px;font-size:13px;font-weight:700;color:#0c1c42">Equipo Web-Impulsa</p>
        <p style="margin:0;font-size:12px;color:#5a6d8c">
          <a href="mailto:info@webimpulsa.es" style="color:#1760d6;text-decoration:none">info@webimpulsa.es</a>
          &nbsp;·&nbsp;
          <a href="https://wa.me/34613708322" style="color:#1760d6;text-decoration:none">+34 613 708 322</a>
        </p>
      </td>
      <td align="right">
        <a href="{cabinet_url}"
           style="display:inline-block;background:#edf4ff;color:#1760d6;font-size:11px;
                  font-weight:700;padding:6px 14px;border-radius:20px;text-decoration:none">
          Mi área →
        </a>
      </td>
    </tr></table>
    <p style="margin:10px 0 0;font-size:11px;color:#cbd5e1;text-align:center">© 2026 Web-Impulsa · España</p>
  </td></tr>

</table>
</td></tr>
</table>
</body>
</html>"""

    plain_client = (
        f'Hola {first},\n\n'
        f'Tu propuesta Web-Impulsa está firmada. Adjunta encontrarás una copia en PDF.\n\n'
        f'Propuesta: {proposal.number} — {proposal.total_with_iva}€ (IVA incl.)\n'
        f'Firmado por: {proposal.accepted_by_name} el {signed_at}\n\n'
        f'Tu área de cliente: {cabinet_url}\n\n'
        f'Nos pondremos en contacto en menos de 24h.\n\n'
        f'Equipo Web-Impulsa\ninfo@webimpulsa.es | +34 613 708 322\n'
    )
    try:
        msg_cli = EmailMultiAlternatives(
            subject=f'✅ Propuesta firmada — {proposal.number} | Web-Impulsa',
            body=plain_client,
            from_email='info@webimpulsa.es',
            to=[lead.email],
            connection=_brevo(),
        )
        msg_cli.attach_alternative(html_client, 'text/html')
        if pdf_bytes:
            msg_cli.attach(pdf_name, pdf_bytes, 'application/pdf')
        msg_cli.send()
        logger.info('Acceptance client email sent to %s for proposal %s',
                    lead.email, proposal.number)
    except Exception as exc:
        logger.error('Acceptance client email failed %s: %s', proposal.number, exc)

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
            'conditionsConsumer': CONDITIONS_CONSUMER,
            'conditionsBusiness': CONDITIONS_BUSINESS,
        }, ensure_ascii=False, default=str)

    materials     = lead.materials.all()
    milestones    = lead.milestones.all()
    status_label  = CLIENT_STATUS_LABEL.get(lead.status, lead.status)
    next_step_msg = CLIENT_NEXT_STEP.get(lead.status, '')

    milestone_list = list(milestones)
    if milestone_list:
        done_n = sum(1 for m in milestone_list if m.status == m.ST_DONE)
        progress_pct = round(100 * done_n / len(milestone_list))
    else:
        progress_pct = CLIENT_STAGE_PROGRESS.get(lead.status)

    _PROPOSAL_STATUSES = (Lead.ST_NUEVO, Lead.ST_CONTACTADO,
                          Lead.ST_PROPUESTA, Lead.ST_NEGOCIACION)
    portal_mode = 'proposal' if lead.status in _PROPOSAL_STATUSES else 'cabinet'

    # Payment status for cabinet
    from .models import PaymentRecord
    payments        = lead.payments.all().order_by('-payment_date')
    payment_pending = payments.filter(status=PaymentRecord.ST_PENDING).first()

    # Accepted proposal for payment amounts
    accepted_proposal = (lead.proposals
                         .filter(status=Proposal.ST_ACCEPTED)
                         .order_by('-created_at')
                         .first())
    invoice_total = accepted_proposal.total_with_iva if accepted_proposal else 0
    paid_total    = sum(p.amount for p in payments.filter(status=PaymentRecord.ST_RECEIVED))
    owed_total    = max(invoice_total - paid_total, 0)

    return render(request, 'crm/portal.html', {
        'step':              'portal',
        'access':            access,
        'lead':              lead,
        'materials':         materials,
        'milestones':        milestones,
        'status_label':      status_label,
        'next_step':         next_step_msg,
        'progress_pct':      progress_pct,
        'wants_materials':   lead.status in (Lead.ST_ACEPTADO, Lead.ST_EN_TRABAJO),
        'proposal':          proposal,
        'proposal_json':     proposal_json,
        'accepted':          request.GET.get('accepted') == '1',
        'portal_mode':       portal_mode,
        'payment_pending':   payment_pending,
        'invoice_total':     invoice_total,
        'paid_total':        paid_total,
        'owed_total':        owed_total,
        'consent_labels':    CONSENT_LABELS,
        'withdrawal_consent_text': WITHDRAWAL_CONSENT_TEXT,
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

    P = request.POST

    client_type  = P.get('client_type', '').strip()
    name         = P.get('accept_name', '').strip()
    nif          = P.get('accept_nif', '').strip()
    address      = P.get('accept_address', '').strip()
    municipality = P.get('accept_municipality', '').strip()
    postal_code  = P.get('accept_postal_code', '').strip()
    province     = P.get('accept_province', '').strip()
    country      = P.get('accept_country', '').strip() or 'España'
    signature    = P.get('accept_signature', '').strip()
    payment_plan = P.get('accept_payment_plan', '').strip()

    rep_name     = P.get('accept_rep_name', '').strip()
    rep_nif      = P.get('accept_rep_nif', '').strip()
    rep_position = P.get('accept_rep_position', '').strip()

    # One combined checkbox covers all the CONSENT_LABELS topics (shown to the
    # client via an info modal) — same audit content, less UI friction than a
    # checkbox per topic. The withdrawal waiver stays separate: it's a distinct
    # statutory right that requires its own explicit action (art. 103.a TRLGDCU).
    consent_keys = list(CONSENT_LABELS.keys())
    consent_all = bool(P.get('consent_all', '').strip())
    consents = {k: consent_all for k in consent_keys}
    withdrawal_waived = bool(P.get('consent_withdrawal', '').strip())

    # ── Validation ──────────────────────────────────────────────────────────
    if client_type not in (Proposal.CLIENT_TYPE_PARTICULAR, Proposal.CLIENT_TYPE_AUTONOMO,
                            Proposal.CLIENT_TYPE_EMPRESA):
        return HttpResponse('Debes indicar el tipo de cliente.', status=400)
    if not name:
        return HttpResponse('El nombre / razón social es obligatorio.', status=400)
    if not nif:
        return HttpResponse('El NIF/NIE/CIF es obligatorio.', status=400)
    if not address or not postal_code or not municipality or not province:
        return HttpResponse('El domicilio fiscal completo (dirección, código postal, municipio y provincia) es obligatorio.', status=400)
    if not signature:
        return HttpResponse('La firma es obligatoria.', status=400)
    if client_type == Proposal.CLIENT_TYPE_EMPRESA and not (rep_name and rep_nif and rep_position):
        return HttpResponse('Para empresas, el nombre, NIF/NIE y cargo del representante son obligatorios.', status=400)
    if client_type == Proposal.CLIENT_TYPE_PARTICULAR and not withdrawal_waived:
        return HttpResponse('Debes confirmar la renuncia al derecho de desistimiento para empezar antes de 14 días.', status=400)
    if not consent_all:
        return HttpResponse('Debes marcar la casilla de confirmación.', status=400)

    # Freeze the correct legal-conditions variant for this client type.
    conditions = (CONDITIONS_BUSINESS
                  if client_type in (Proposal.CLIENT_TYPE_AUTONOMO, Proposal.CLIENT_TYPE_EMPRESA)
                  else CONDITIONS_CONSUMER)

    # Save fiscal data + audit trail BEFORE accept_proposal (so it's in the PDF)
    proposal.client_type          = client_type
    proposal.client_address       = address[:300]
    proposal.client_city          = municipality[:100]
    proposal.client_postal_code   = postal_code[:10]
    proposal.client_province      = province[:100]
    proposal.client_country       = country[:100]
    proposal.client_nif           = nif[:30]
    proposal.representative_name     = rep_name[:200]
    proposal.representative_nif      = rep_nif[:30]
    proposal.representative_position = rep_position[:100]
    proposal.conditions           = conditions[:]
    proposal.accepted_consents    = consents
    proposal.withdrawal_waived    = withdrawal_waived
    proposal.accepted_ip          = _client_ip(request)[:45]
    proposal.accepted_user_agent  = request.META.get('HTTP_USER_AGENT', '')[:500]
    if payment_plan in dict(PAYMENT_PLAN_CHOICES):
        proposal.payment_method = payment_plan
    proposal.save(update_fields=[
        'client_type', 'client_address', 'client_city', 'client_postal_code', 'client_province',
        'client_country', 'client_nif', 'representative_name', 'representative_nif',
        'representative_position', 'conditions', 'accepted_consents', 'withdrawal_waived',
        'accepted_ip', 'accepted_user_agent', 'payment_method', 'updated_at',
    ])

    accept_proposal(proposal, name, nif, signature)

    # Generate the signed PDF once: persist an immutable copy + hash for tamper-evidence,
    # then reuse the same bytes for the acceptance emails below (avoids rendering twice).
    pdf_bytes = None
    try:
        from .pdf import generate_proposal_pdf
        pdf_bytes = generate_proposal_pdf(proposal)
        if pdf_bytes:
            proposal.accepted_pdf_sha256 = hashlib.sha256(pdf_bytes).hexdigest()
            proposal.accepted_pdf.save(
                f'{proposal.number}.pdf', ContentFile(pdf_bytes), save=False,
            )
            proposal.save(update_fields=['accepted_pdf', 'accepted_pdf_sha256'])
    except Exception as exc:
        logger.error('Could not persist signed PDF snapshot for %s: %s', proposal.number, exc)

    logger.info('Proposal %s accepted via portal: lead #%d by %s (%s)',
                proposal.number, lead.pk, name, client_type)

    tg_text = (
        f'✅ <b>Propuesta aceptada</b>\n'
        f'Cliente: {name} ({nif or "sin NIF"}) — {client_type}\n'
        f'Propuesta: {proposal.number} — {proposal.total_with_iva}€\n'
        f'→ https://webimpulsa.es/wi/crm/{lead.pk}/'
    )
    _notify_tg(tg_text)
    _notify_wa(
        f'✅ PROPUESTA ACEPTADA\n'
        f'Cliente: {name} ({client_type})\nNIF: {nif or "—"}\n'
        f'Propuesta: {proposal.number} — {proposal.total_with_iva}€\n'
        f'CRM: https://webimpulsa.es/wi/crm/{lead.pk}/'
    )

    try:
        _send_acceptance_emails(proposal, access, pdf_bytes=pdf_bytes)
    except Exception as exc:
        logger.error('Acceptance emails failed for proposal %s: %s', proposal.number, exc)

    return redirect(f'/p/{token}/pay/')


# ── PWA manifest (per-client "Add to Home Screen" shortcut) ───────────────────

@require_http_methods(['GET'])
def portal_manifest(request, token):
    """GET /p/<token>/manifest.json — lets the client add a home-screen shortcut
    straight to their own portal, so they don't have to dig up the email link."""
    access = validate_portal_token(token)
    if access is None:
        raise Http404('Token inválido o expirado')

    icon = '/static/wi/img/apple-icon.png'
    manifest = {
        'name': f'Web-Impulsa — {access.lead.name}',
        'short_name': 'Mi proyecto',
        'start_url': f'/p/{token}/',
        'scope': f'/p/{token}/',
        'display': 'standalone',
        'background_color': '#eef3ff',
        'theme_color': '#1760d6',
        'icons': [
            {'src': icon, 'sizes': '180x180', 'type': 'image/png'},
            {'src': icon, 'sizes': '192x192', 'type': 'image/png', 'purpose': 'any'},
            {'src': icon, 'sizes': '512x512', 'type': 'image/png', 'purpose': 'any'},
        ],
    }
    return JsonResponse(manifest, content_type='application/manifest+json')


@require_http_methods(['GET'])
def portal_sw(request, token):
    """GET /p/<token>/sw.js — a no-op service worker.

    Its only purpose is to satisfy Chrome's installability criteria for the
    "Add to Home Screen" shortcut (beforeinstallprompt won't fire without a
    registered service worker). Served under /p/<token>/ so its default scope
    covers exactly this client's portal pages, nothing else.
    """
    js = "self.addEventListener('fetch', function() {});"
    return HttpResponse(js, content_type='application/javascript')


# ── Client message ────────────────────────────────────────────────────────────


@require_http_methods(['GET'])
def portal_messages(request, token):
    """GET /p/<token>/messages/ — JSON message list for polling; marks team msgs as read."""
    access = validate_portal_token(token)
    if access is None:
        return JsonResponse({'ok': False, 'error': 'Token inválido o expirado'}, status=403)

    needs_pin = access.pin_required and not _is_pin_verified(request, token)
    if needs_pin:
        return JsonResponse({'ok': False, 'error': 'PIN no verificado'}, status=403)

    lead = access.lead
    msgs = (lead.comm_log.filter(channel=CommunicationLog.CH_PORTAL)
            .exclude(content__startswith='Cliente verificó')
            .exclude(content__startswith='Propuesta ')
            .exclude(content__startswith='Enlace de acceso')
            .select_related('reply_to')
            .order_by('created_at')[:200])

    # Client is actively viewing the chat — mark team messages as read
    unread_ids = [m.pk for m in msgs
                  if m.direction == CommunicationLog.DIR_OUTBOUND and m.read_at is None]
    if unread_ids:
        from django.utils import timezone as tz
        CommunicationLog.objects.filter(pk__in=unread_ids).update(read_at=tz.now())

    # Bump presence heartbeat so Tatiana's CRM can show "client online / last seen"
    ClientAccess.objects.filter(pk=access.pk).update(last_access=timezone.now())

    return JsonResponse({
        'ok': True,
        'messages': [serialize_chat_message(m) for m in msgs],
        'admin_online': _admin_is_online(lead),
        'admin_last_seen': lead.admin_chat_seen_at.isoformat() if lead.admin_chat_seen_at else None,
    })


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

    reply_to = None
    reply_to_id = request.POST.get('reply_to', '').strip()
    if reply_to_id.isdigit():
        reply_to = lead.comm_log.filter(pk=int(reply_to_id), channel=CommunicationLog.CH_PORTAL).first()

    msg = CommunicationLog.objects.create(
        lead=lead,
        direction=CommunicationLog.DIR_INBOUND,
        channel=CommunicationLog.CH_PORTAL,
        content=text,
        status=CommunicationLog.ST_DELIVERED,
        reply_to=reply_to,
    )

    if not _admin_is_online(lead):
        notify_text = (
            f'💬 <b>Mensaje del portal</b> — {lead.name}\n'
            f'Proyecto: {lead.package or "—"}\n\n'
            f'{text}\n\n'
            f'→ https://webimpulsa.es/wi/crm/{lead.pk}/'
        )
        _notify_tg(notify_text)
        _notify_wa(
            f'💬 Mensaje portal — {lead.name}\n'
            f'{text}\n'
            f'CRM: https://webimpulsa.es/wi/crm/{lead.pk}/'
        )

    return JsonResponse({'ok': True, 'message': serialize_chat_message(msg)})


@csrf_exempt
@require_http_methods(['POST'])
def portal_react_message(request, token, pk):
    """POST /p/<token>/message/<pk>/react/ — client toggles an emoji reaction."""
    access = validate_portal_token(token)
    if access is None:
        return JsonResponse({'ok': False, 'error': 'Token inválido o expirado'}, status=403)

    needs_pin = access.pin_required and not _is_pin_verified(request, token)
    if needs_pin:
        return JsonResponse({'ok': False, 'error': 'PIN no verificado'}, status=403)

    emoji = (request.POST.get('emoji') or '').strip()
    if not emoji:
        return JsonResponse({'ok': False, 'error': 'Falta el emoji'}, status=400)

    msg = get_object_or_404(access.lead.comm_log, pk=pk, channel=CommunicationLog.CH_PORTAL)
    reactions = list(msg.reactions or [])
    existing = next((r for r in reactions if r.get('by') == 'client'), None)

    if existing and existing.get('emoji') == emoji:
        reactions = [r for r in reactions if r.get('by') != 'client']  # toggle off
    elif existing:
        existing['emoji'] = emoji  # replace client's previous reaction
    else:
        reactions.append({'emoji': emoji, 'by': 'client'})

    msg.reactions = reactions
    msg.save(update_fields=['reactions'])

    return JsonResponse({'ok': True, 'reactions': reactions})


@csrf_exempt
@require_http_methods(['POST'])
def portal_delete_message(request, token, pk):
    """POST /p/<token>/message/<pk>/delete/ — client soft-deletes their own message."""
    access = validate_portal_token(token)
    if access is None:
        return JsonResponse({'ok': False, 'error': 'Token inválido o expirado'}, status=403)

    needs_pin = access.pin_required and not _is_pin_verified(request, token)
    if needs_pin:
        return JsonResponse({'ok': False, 'error': 'PIN no verificado'}, status=403)

    msg = get_object_or_404(
        access.lead.comm_log, pk=pk,
        channel=CommunicationLog.CH_PORTAL, direction=CommunicationLog.DIR_INBOUND,
    )
    msg.deleted = True
    msg.save(update_fields=['deleted'])

    return JsonResponse({'ok': True})


# ── Payment page ──────────────────────────────────────────────────────────────

_PAY_IBAN   = os.getenv('WI_PAYMENT_IBAN', '')
_PAY_HOLDER = os.getenv('WI_PAYMENT_HOLDER', 'Tatiana Gorbunova')
_PAY_BIZUM  = os.getenv('WI_PAYMENT_BIZUM', '613708322')
_STRIPE_SECRET_KEY = os.getenv('STRIPE_SECRET_KEY', '')


@require_http_methods(['GET'])
def portal_pay(request, token):
    """GET /p/<token>/pay/ — payment instructions page shown after signing."""
    access = validate_portal_token(token)
    if access is None:
        return redirect(f'/p/{token}/')

    needs_pin = access.pin_required and not _is_pin_verified(request, token)
    if needs_pin:
        return redirect(f'/p/{token}/')

    lead = access.lead
    proposal = (lead.proposals
                .filter(status=Proposal.ST_ACCEPTED)
                .order_by('-created_at')
                .first())

    sched    = payment_schedule(proposal) if proposal else {'first_amount': 0, 'first_label': 'Primer pago', 'schedule_text': ''}
    half     = sched['first_amount']
    concepto = f'{proposal.number} {lead.name}' if proposal else lead.name

    return render(request, 'crm/portal.html', {
        'step':      'pay',
        'access':    access,
        'lead':      lead,
        'proposal':  proposal,
        'half':      half,
        'pay_label':      sched['first_label'],
        'pay_schedule':   sched['schedule_text'],
        'concepto':  concepto,
        'iban':            _PAY_IBAN,
        'holder':          _PAY_HOLDER,
        'bizum':           _PAY_BIZUM,
        'paid_ok':         request.GET.get('paid') == '1',
        'card_ok':         request.GET.get('card') == '1',
        'stripe_enabled':  bool(_STRIPE_SECRET_KEY),
        'stripe_error':    request.GET.get('stripe_error') == '1',
    })


@require_http_methods(['POST'])
def portal_pay_stripe_start(request, token):
    """POST /p/<token>/pay/stripe/ — create a Stripe Checkout Session and redirect to it."""
    access = validate_portal_token(token)
    if access is None:
        return redirect(f'/p/{token}/')

    needs_pin = access.pin_required and not _is_pin_verified(request, token)
    if needs_pin:
        return redirect(f'/p/{token}/')

    if not _STRIPE_SECRET_KEY:
        return redirect(f'/p/{token}/pay/?stripe_error=1')

    lead     = access.lead
    proposal = (lead.proposals
                .filter(status=Proposal.ST_ACCEPTED)
                .order_by('-created_at')
                .first())
    sched = payment_schedule(proposal) if proposal else {'first_amount': 0, 'first_label': 'Primer pago'}
    half  = sched['first_amount']
    if half <= 0:
        return redirect(f'/p/{token}/pay/?stripe_error=1')

    concepto = f'{proposal.number} {lead.name}' if proposal else lead.name

    import stripe
    stripe.api_key = _STRIPE_SECRET_KEY
    try:
        session = stripe.checkout.Session.create(
            mode='payment',
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'eur',
                    'unit_amount': half * 100,
                    'product_data': {'name': f'{sched["first_label"]} — {concepto}'},
                },
                'quantity': 1,
            }],
            success_url=f'{_BASE_URL}/p/{token}/pay/stripe/success/?session_id={{CHECKOUT_SESSION_ID}}',
            cancel_url=f'{_BASE_URL}/p/{token}/pay/',
            client_reference_id=token,
        )
    except Exception as exc:
        logger.error('Stripe Checkout Session creation failed for %s: %s', token, exc)
        return redirect(f'/p/{token}/pay/?stripe_error=1')

    return redirect(session.url, permanent=False)


@require_http_methods(['GET'])
def portal_pay_stripe_success(request, token):
    """GET /p/<token>/pay/stripe/success/ — verify the Checkout Session and record the payment."""
    from django.utils.timezone import localdate
    from .models import PaymentRecord

    access = validate_portal_token(token)
    if access is None:
        return redirect(f'/p/{token}/')

    session_id = request.GET.get('session_id', '')
    if not (_STRIPE_SECRET_KEY and session_id):
        return redirect(f'/p/{token}/pay/')

    import stripe
    stripe.api_key = _STRIPE_SECRET_KEY
    try:
        session = stripe.checkout.Session.retrieve(session_id)
    except Exception as exc:
        logger.error('Stripe session retrieve failed for %s: %s', token, exc)
        return redirect(f'/p/{token}/pay/?stripe_error=1')

    if session.payment_status != 'paid':
        return redirect(f'/p/{token}/pay/')

    lead = access.lead
    # Avoid creating a duplicate record if the success page is reloaded
    if PaymentRecord.objects.filter(reference=session_id).exists():
        return redirect(f'/p/{token}/pay/?paid=1&card=1')

    proposal = (lead.proposals
                .filter(status=Proposal.ST_ACCEPTED)
                .order_by('-created_at')
                .first())
    sched = payment_schedule(proposal) if proposal else None
    half  = sched['first_amount'] if sched else (session.amount_total or 0) // 100
    label = sched['first_label'] if sched else 'Pago'

    PaymentRecord.objects.create(
        lead         = lead,
        concept      = f'{label} — tarjeta (Stripe)',
        amount       = half,
        payment_date = localdate(),
        method       = PaymentRecord.MT_STRIPE,
        status       = PaymentRecord.ST_RECEIVED,
        reference    = session_id,
        notes        = 'Pago con tarjeta confirmado automáticamente por Stripe Checkout.',
    )

    log_communication(
        lead=lead,
        direction=CommunicationLog.DIR_INBOUND,
        channel=CommunicationLog.CH_PORTAL,
        content=f'Cliente pagó {half}€ con tarjeta (Stripe).',
        status=CommunicationLog.ST_DELIVERED,
    )

    _notify_tg(
        f'💳✅ <b>Pago con tarjeta recibido</b>\n'
        f'Cliente: {lead.name}\n'
        f'Importe: {half}€ · Stripe\n'
        f'→ <a href="https://webimpulsa.es/wi/crm/{lead.pk}/">CRM</a>'
    )
    _notify_wa(
        f'💳✅ PAGO CON TARJETA RECIBIDO\n'
        f'Cliente: {lead.name}\n'
        f'Importe: {half}€ · Stripe\n'
        f'CRM: https://webimpulsa.es/wi/crm/{lead.pk}/'
    )

    return redirect(f'/p/{token}/pay/?paid=1&card=1')


@csrf_exempt
@require_http_methods(['POST'])
def portal_client_paid(request, token):
    """POST /p/<token>/pay/notify/ — client clicks 'I've made the transfer'."""
    from django.utils import timezone as tz

    access = validate_portal_token(token)
    if access is None:
        return HttpResponse('Enlace inválido.', status=403)

    lead     = access.lead
    proposal = (lead.proposals
                .filter(status=Proposal.ST_ACCEPTED)
                .order_by('-created_at')
                .first())
    method = request.POST.get('method', 'bank_transfer')

    # Create a pending PaymentRecord so Tatiana can confirm it
    from .models import PaymentRecord
    from django.utils.timezone import localdate

    sched = payment_schedule(proposal) if proposal else {'first_amount': 0, 'first_label': 'Primer pago'}
    half  = sched['first_amount']
    method_label = dict(PaymentRecord.METHOD_CHOICES).get(method, method)
    concept = f'{sched["first_label"]} — notificado por cliente ({method_label})'

    pay = PaymentRecord.objects.create(
        lead         = lead,
        concept      = concept,
        amount       = half,
        payment_date = localdate(),
        method       = method,
        status       = PaymentRecord.ST_PENDING,
        notes        = f'Notificado por el cliente desde el portal. Pendiente de confirmar recepción.',
    )

    log_communication(
        lead=lead,
        direction=CommunicationLog.DIR_INBOUND,
        channel=CommunicationLog.CH_PORTAL,
        content=f'Cliente notificó pago de {half}€ por {method_label}.',
        status=CommunicationLog.ST_DELIVERED,
    )

    _notify_tg(
        f'💳 <b>Pago notificado por cliente</b>\n'
        f'Cliente: {lead.name}\n'
        f'Importe: {half}€ · {method_label}\n'
        f'Estado: pendiente de confirmar\n'
        f'→ <a href="https://webimpulsa.es/wi/crm/{lead.pk}/">CRM</a>'
    )
    _notify_wa(
        f'💳 PAGO NOTIFICADO\n'
        f'Cliente: {lead.name}\n'
        f'Importe: {half}€ · {method_label}\n'
        f'Confirmar en CRM: https://webimpulsa.es/wi/crm/{lead.pk}/'
    )

    return redirect(f'/p/{token}/pay/?paid=1')
