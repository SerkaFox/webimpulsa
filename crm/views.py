import base64
import functools
import json
import logging
import os
from datetime import date

from django.core.mail import send_mail, get_connection, EmailMultiAlternatives
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from .models import (
    CommunicationLog, EvidenceFile, Lead, PaymentRecord,
    ProjectMaterial, ProjectMilestone, WorkLog,
)
from .services import (
    generate_client_access, lead_from_payload, log_communication,
    mark_proposal_sent, create_proposal_from_lead, NEXT_STEPS,
)
from .wa_templates import compose_portal_message, compose_materials_request

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

def _mailcow_connection():
    """Direct connection to local Mailcow — for internal @webimpulsa.es delivery."""
    return get_connection(
        backend='django.core.mail.backends.smtp.EmailBackend',
        host='127.0.0.1', port=25, use_tls=False,
        username='', password='',
    )


def _brevo_connection():
    """Brevo SMTP relay — for external delivery (Gmail, etc.)."""
    return get_connection(
        backend='django.core.mail.backends.smtp.EmailBackend',
        host=os.getenv('BREVO_HOST', 'smtp-relay.brevo.com'),
        port=int(os.getenv('BREVO_PORT', 587)),
        use_tls=True,
        username=os.getenv('BREVO_USER', ''),
        password=os.getenv('BREVO_PASS', ''),
    )


def _send_lead_emails(lead) -> None:
    from .pdf import generate_proposal_pdf
    from .docx_gen import generate_proposal_docx

    pkg     = lead.package or '—'
    price_s = f'{lead.estimated_price} €' if lead.estimated_price else '—'
    contact = lead.email or lead.phone or '—'
    biz     = lead.biz_type or '—'

    # ── 1. Internal notification to Tatiana via Mailcow ───────────────────────
    subject_tanya = f'📋 Nueva solicitud — {lead.name} | {pkg} | {price_s}'
    body_tanya = (
        f"Nueva solicitud en webimpulsa.es\n"
        f"{'─'*40}\n"
        f"Nombre:   {lead.name}\n"
        f"Contacto: {contact}\n"
        f"Negocio:  {biz}\n"
        f"{'─'*40}\n"
        f"Proyecto:    {pkg}\n"
        f"Presupuesto: {price_s}\n\n"
        f"→ CRM: https://webimpulsa.es/wi/crm/leads/{lead.pk}/\n"
    )
    try:
        send_mail(subject_tanya, body_tanya, 'info@webimpulsa.es',
                  ['info@webimpulsa.es'], connection=_mailcow_connection())
    except Exception as exc:
        logger.error('Lead notify email failed #%d: %s', lead.pk, exc)

    if not lead.email:
        return

    # ── 2. Create proposal + portal access ───────────────────────────────────
    try:
        proposal = create_proposal_from_lead(lead)
        mark_proposal_sent(proposal)
        _, portal_url, _ = generate_client_access(lead, pin_required=False, expires_hours=168)
    except Exception as exc:
        logger.error('Proposal/portal setup failed #%d: %s', lead.pk, exc)
        proposal  = None
        portal_url = 'https://webimpulsa.es'

    # ── 3. Generate attachments ───────────────────────────────────────────────
    pdf_bytes  = generate_proposal_pdf(proposal) if proposal else None
    docx_bytes = generate_proposal_docx(proposal) if proposal else None
    safe_name  = ''.join(c if c.isalnum() or c in '-_' else '_' for c in lead.name)

    # ── 4. Build HTML email ───────────────────────────────────────────────────
    first   = (lead.name.split()[0] if lead.name else lead.name)
    biz_row = (
        f'<tr><td style="padding:4px 0;color:#5a6d8c;font-size:13px">Tipo de negocio</td>'
        f'<td style="padding:4px 0;font-weight:600;font-size:13px">{biz}</td></tr>'
        if biz != '—' else ''
    )
    plain_text = (
        f"Hola {lead.name},\n\n"
        f"Tu propuesta está lista — la encontrarás adjunta (PDF y Word).\n"
        f"También puedes revisarla y aceptarla online: {portal_url}\n\n"
        f"Proyecto: {pkg}\nPresupuesto: {price_s}\n\n"
        f"info@webimpulsa.es | +34 613 708 322 | webimpulsa.es\n"
    )
    html_client = f"""<!DOCTYPE html>
<html lang="es">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f0f4f8;font-family:'Segoe UI',Arial,Helvetica,sans-serif">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f0f4f8;padding:28px 12px">
<tr><td align="center">
<table width="580" cellpadding="0" cellspacing="0" style="max-width:580px;width:100%;background:#ffffff;border-radius:10px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,.07)">

  <!-- Logo bar -->
  <tr>
    <td style="padding:20px 32px 16px;border-bottom:3px solid #1760d6">
      <table width="100%" cellpadding="0" cellspacing="0"><tr>
        <td><img src="https://webimpulsa.es/static/wi/img/logo.webp" alt="WebImpulsa" height="36" style="display:block"></td>
        <td align="right" style="font-size:12px;color:#5a6d8c"><a href="https://webimpulsa.es" style="color:#1760d6;text-decoration:none;font-weight:600">webimpulsa.es</a></td>
      </tr></table>
    </td>
  </tr>

  <!-- Greeting -->
  <tr><td style="padding:26px 32px 0">
    <p style="font-size:20px;font-weight:800;color:#0c1c42;margin:0 0 8px">Hola {first} 👋</p>
    <p style="font-size:14px;color:#5a6d8c;line-height:1.65;margin:0 0 20px">
      Tu propuesta personalizada está lista. Tienes <strong style="color:#0c1c42">dos opciones</strong>:
      revisarla online o descargar los archivos adjuntos (PDF y Word).
    </p>
  </td></tr>

  <!-- CTA portal -->
  <tr><td style="padding:0 32px 20px">
    <a href="{portal_url}"
       style="display:block;background:#1760d6;color:#ffffff;text-decoration:none;
              text-align:center;padding:14px 24px;border-radius:8px;
              font-size:15px;font-weight:800;letter-spacing:.01em">
      Ver y aceptar propuesta online →
    </a>
    <p style="font-size:11px;color:#94a3b8;text-align:center;margin:8px 0 0">
      El enlace es personal y caduca en 7 días
    </p>
  </td></tr>

  <!-- Divider -->
  <tr><td style="padding:0 32px 20px">
    <table width="100%" cellpadding="0" cellspacing="0">
      <tr>
        <td style="border-top:1px solid #e2e8f0"></td>
        <td style="padding:0 12px;white-space:nowrap;font-size:11px;color:#94a3b8">o descarga los adjuntos</td>
        <td style="border-top:1px solid #e2e8f0"></td>
      </tr>
    </table>
  </td></tr>

  <!-- Attachments note -->
  <tr><td style="padding:0 32px 24px">
    <table width="100%" cellpadding="0" cellspacing="0">
      <tr>
        <td width="48%" style="background:#f5f9ff;border:1px solid #d0e1fa;border-radius:8px;padding:12px 14px">
          <p style="margin:0 0 3px;font-size:12px;font-weight:700;color:#0c1c42">📄 PDF</p>
          <p style="margin:0;font-size:11px;color:#5a6d8c">Para imprimir o firmar a mano</p>
        </td>
        <td width="4%"></td>
        <td width="48%" style="background:#f5f9ff;border:1px solid #d0e1fa;border-radius:8px;padding:12px 14px">
          <p style="margin:0 0 3px;font-size:12px;font-weight:700;color:#0c1c42">📝 Word</p>
          <p style="margin:0;font-size:11px;color:#5a6d8c">Para editar tus datos (NIF, dirección)</p>
        </td>
      </tr>
    </table>
  </td></tr>

  <!-- Summary box -->
  <tr><td style="padding:0 32px 26px">
    <table width="100%" cellpadding="0" cellspacing="0"
           style="background:#f5f9ff;border-left:4px solid #1760d6;border-radius:0 8px 8px 0;padding:16px 18px">
      <tr><td>
        <p style="font-size:10px;font-weight:700;color:#1760d6;text-transform:uppercase;letter-spacing:.08em;margin:0 0 10px">Tu proyecto</p>
        <table width="100%" cellpadding="0" cellspacing="0" style="color:#0c1c42">
          <tr>
            <td style="padding:4px 0;color:#5a6d8c;font-size:13px;width:44%">Paquete</td>
            <td style="padding:4px 0;font-weight:700;font-size:13px">{pkg}</td>
          </tr>
          <tr>
            <td style="padding:2px 0;color:#5a6d8c;font-size:13px">Presupuesto</td>
            <td style="padding:2px 0;font-weight:700;font-size:15px;color:#1760d6">{price_s} + IVA</td>
          </tr>
          {biz_row}
        </table>
      </td></tr>
    </table>
  </td></tr>

  <!-- Footer -->
  <tr><td style="padding:16px 32px;background:#f8fafc;border-top:1px solid #e2e8f0">
    <table width="100%" cellpadding="0" cellspacing="0"><tr>
      <td>
        <p style="margin:0 0 2px;font-size:13px;font-weight:700;color:#0c1c42">Equipo WebImpulsa</p>
        <p style="margin:0;font-size:12px;color:#5a6d8c">
          <a href="mailto:info@webimpulsa.es" style="color:#1760d6;text-decoration:none">info@webimpulsa.es</a>
          &nbsp;·&nbsp;
          <a href="https://wa.me/34613708322" style="color:#1760d6;text-decoration:none">+34 613 708 322</a>
        </p>
      </td>
      <td align="right">
        <a href="{portal_url}" style="display:inline-block;background:#edf4ff;color:#1760d6;font-size:11px;font-weight:700;padding:6px 14px;border-radius:20px;text-decoration:none">Portal →</a>
      </td>
    </tr></table>
    <p style="margin:10px 0 0;font-size:11px;color:#cbd5e1;text-align:center">© 2026 WebImpulsa · España</p>
  </td></tr>

</table>
</td></tr>
</table>
</body>
</html>"""

    # ── 5. Send email with attachments ────────────────────────────────────────
    try:
        subject_client = f'Tu propuesta WebImpulsa — {pkg}'
        msg = EmailMultiAlternatives(
            subject=subject_client,
            body=plain_text,
            from_email='info@webimpulsa.es',
            to=[lead.email],
            connection=_brevo_connection(),
        )
        msg.attach_alternative(html_client, 'text/html')
        if pdf_bytes:
            msg.attach(f'Propuesta_WebImpulsa_{safe_name}.pdf', pdf_bytes, 'application/pdf')
        if docx_bytes:
            msg.attach(f'Propuesta_WebImpulsa_{safe_name}.docx', docx_bytes,
                       'application/vnd.openxmlformats-officedocument.wordprocessingml.document')
        msg.send()
        logger.info('Client email sent to %s (pdf=%s docx=%s portal=%s)',
                    lead.email, bool(pdf_bytes), bool(docx_bytes), portal_url)
    except Exception as exc:
        logger.error('Lead client email failed #%d: %s', lead.pk, exc)


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
        _send_lead_emails(lead)
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
        new_channel = request.POST.get('preferred_channel', lead.preferred_channel)
        if new_status in dict(Lead.STATUS_CHOICES):
            lead.status = new_status
        if new_channel in dict(Lead.CHANNEL_CHOICES):
            lead.preferred_channel = new_channel
        lead.notes = new_notes
        lead.save(update_fields=['status', 'notes', 'preferred_channel', 'updated_at'])

    # Latest active access token
    active_access = lead.access_tokens.filter(is_active=True).order_by('-created_at').first()
    comm_log      = lead.comm_log.all()[:20]
    materials     = lead.materials.all()

    milestones  = lead.milestones.all()
    work_logs   = lead.work_logs.all()
    payments    = lead.payments.all()
    evidence    = lead.evidence.all()

    total_hours  = sum(float(w.hours) for w in work_logs) if work_logs else 0
    total_income = sum(p.amount for p in payments if p.status == PaymentRecord.ST_RECEIVED)

    return render(request, 'crm/lead_detail.html', {
        'lead':               lead,
        'statuses':           Lead.STATUS_CHOICES,
        'channels':           Lead.CHANNEL_CHOICES,
        'status_css':         STATUS_CSS,
        'active_access':      active_access,
        'comm_log':           comm_log,
        'materials':          materials,
        'next_step':          NEXT_STEPS.get(lead.status, ''),
        'comm_channels':      CommunicationLog.CHANNEL_CHOICES,
        'comm_dirs':          CommunicationLog.DIRECTION_CHOICES,
        'milestones':         milestones,
        'work_logs':          work_logs,
        'payments':           payments,
        'evidence':           evidence,
        'total_hours':        total_hours,
        'total_income':       total_income,
        'milestone_choices':  ProjectMilestone.STATUS_CHOICES,
        'worklog_categories': WorkLog.CATEGORY_CHOICES,
        'payment_methods':    PaymentRecord.METHOD_CHOICES,
        'payment_statuses':   PaymentRecord.STATUS_CHOICES,
        'evidence_categories': EvidenceFile.CATEGORY_CHOICES,
    })


# ── CRM action endpoints (AJAX, protected by basic auth) ─────────────────────

@_crm_auth
@csrf_exempt
@require_POST
def lead_generate_access(request, pk):
    """Generate a new magic-link + PIN for the client portal."""
    lead = get_object_or_404(Lead, pk=pk)
    pin_required = request.POST.get('pin_required', 'true') != 'false'
    expires_h    = int(request.POST.get('expires_hours', 72))

    access, portal_url, pin = generate_client_access(
        lead, expires_hours=expires_h, pin_required=pin_required
    )

    wa_msg = compose_portal_message(lead.name, portal_url, pin)

    return JsonResponse({
        'ok':        True,
        'portal_url': portal_url,
        'pin':       pin,
        'wa_message': wa_msg,
        'expires_h': expires_h,
    })


@_crm_auth
@csrf_exempt
@require_POST
def lead_log_comm(request, pk):
    """Manually log a communication entry for this lead."""
    lead      = get_object_or_404(Lead, pk=pk)
    direction = request.POST.get('direction', CommunicationLog.DIR_OUTBOUND)
    channel   = request.POST.get('channel', CommunicationLog.CH_MANUAL)
    content   = (request.POST.get('content') or '').strip()
    template  = request.POST.get('template_name', '')
    notes     = request.POST.get('notes', '')

    if not content:
        return JsonResponse({'ok': False, 'error': 'content required'}, status=400)

    entry = log_communication(
        lead=lead,
        direction=direction,
        channel=channel,
        content=content,
        template_name=template,
        notes=notes,
        status=CommunicationLog.ST_SENT,
    )
    return JsonResponse({'ok': True, 'id': entry.pk})


@_crm_auth
def lead_materials(request, pk):
    """List all materials for a lead (JSON)."""
    lead      = get_object_or_404(Lead, pk=pk)
    materials = lead.materials.all()
    return JsonResponse({
        'ok': True,
        'materials': [
            {
                'id':       m.pk,
                'name':     m.original_filename,
                'type':     m.file_type,
                'size':     m.size_display,
                'source':   m.source,
                'notes':    m.notes,
                'uploaded': m.created_at.isoformat(),
            }
            for m in materials
        ],
    })


# ── Activity / dossier AJAX endpoints ─────────────────────────────────────────

@_crm_auth
@csrf_exempt
@require_POST
def lead_add_milestone(request, pk):
    """POST /wi/crm/<pk>/milestone/ — add a project milestone."""
    lead  = get_object_or_404(Lead, pk=pk)
    title = (request.POST.get('title') or '').strip()
    if not title:
        return JsonResponse({'ok': False, 'error': 'title required'}, status=400)

    m = ProjectMilestone.objects.create(
        lead        = lead,
        title       = title,
        description = request.POST.get('description', ''),
        due_date    = request.POST.get('due_date') or None,
        status      = request.POST.get('status', ProjectMilestone.ST_PENDING),
        notes       = request.POST.get('notes', ''),
    )
    return JsonResponse({'ok': True, 'id': m.pk, 'title': m.title, 'status': m.status})


@_crm_auth
@csrf_exempt
@require_POST
def lead_update_milestone(request, pk, mid):
    """POST /wi/crm/<pk>/milestone/<mid>/ — update a milestone's status/notes."""
    lead = get_object_or_404(Lead, pk=pk)
    m    = get_object_or_404(ProjectMilestone, pk=mid, lead=lead)

    if 'status' in request.POST:
        new_status = request.POST['status']
        if new_status in dict(ProjectMilestone.STATUS_CHOICES):
            m.status = new_status
            if new_status == ProjectMilestone.ST_DONE and not m.completed_date:
                m.completed_date = date.today()
    if 'notes' in request.POST:
        m.notes = request.POST['notes']
    if 'completed_date' in request.POST:
        m.completed_date = request.POST['completed_date'] or None
    m.save()
    return JsonResponse({'ok': True})


@_crm_auth
@csrf_exempt
@require_POST
def lead_add_worklog(request, pk):
    """POST /wi/crm/<pk>/worklog/ — log work hours."""
    lead = get_object_or_404(Lead, pk=pk)
    log_date    = (request.POST.get('date') or '').strip()
    description = (request.POST.get('description') or '').strip()
    if not log_date:
        return JsonResponse({'ok': False, 'error': 'date required'}, status=400)
    if not description:
        return JsonResponse({'ok': False, 'error': 'description required'}, status=400)

    try:
        hours = float(request.POST.get('hours', '1.0') or '1.0')
    except (ValueError, TypeError):
        hours = 1.0

    w = WorkLog.objects.create(
        lead            = lead,
        date            = log_date,
        hours           = hours,
        category        = request.POST.get('category', WorkLog.CAT_DEVELOPMENT),
        description     = description,
        deliverable_url = request.POST.get('deliverable_url', ''),
        notes           = request.POST.get('notes', ''),
    )
    return JsonResponse({'ok': True, 'id': w.pk})


@_crm_auth
@csrf_exempt
@require_POST
def lead_add_payment(request, pk):
    """POST /wi/crm/<pk>/payment/ — record a payment (multipart, may include invoice_file)."""
    lead = get_object_or_404(Lead, pk=pk)
    concept      = (request.POST.get('concept') or '').strip()
    payment_date = (request.POST.get('payment_date') or '').strip()
    try:
        amount = int(request.POST.get('amount', 0))
    except (ValueError, TypeError):
        return JsonResponse({'ok': False, 'error': 'amount must be integer'}, status=400)

    if not concept:
        return JsonResponse({'ok': False, 'error': 'concept required'}, status=400)
    if not payment_date:
        return JsonResponse({'ok': False, 'error': 'payment_date required'}, status=400)

    p = PaymentRecord(
        lead         = lead,
        concept      = concept,
        amount       = amount,
        payment_date = payment_date,
        method       = request.POST.get('method', PaymentRecord.MT_BANK_TRANSFER),
        reference    = request.POST.get('reference', ''),
        status       = request.POST.get('status', PaymentRecord.ST_RECEIVED),
        notes        = request.POST.get('notes', ''),
    )
    if 'invoice_file' in request.FILES:
        p.invoice_file = request.FILES['invoice_file']
    p.save()
    return JsonResponse({'ok': True, 'id': p.pk})


@_crm_auth
@csrf_exempt
@require_POST
def lead_add_evidence(request, pk):
    """POST /wi/crm/<pk>/evidence/ — add evidence file/URL (multipart)."""
    lead  = get_object_or_404(Lead, pk=pk)
    title = (request.POST.get('title') or '').strip()
    if not title:
        return JsonResponse({'ok': False, 'error': 'title required'}, status=400)

    e = EvidenceFile(
        lead     = lead,
        category = request.POST.get('category', EvidenceFile.CAT_OTHER),
        title    = title,
        url      = request.POST.get('url', ''),
        notes    = request.POST.get('notes', ''),
    )
    if 'file' in request.FILES:
        e.file = request.FILES['file']
    e.save()
    return JsonResponse({'ok': True, 'id': e.pk})


@_crm_auth
@require_GET
def serve_invoice(request, pk):
    """GET /wi/crm/payment/<pk>/invoice/ — serve PaymentRecord invoice file."""
    p = get_object_or_404(PaymentRecord, pk=pk)
    if not p.invoice_file or not p.invoice_file.name:
        raise Http404('No invoice file attached')
    try:
        f = p.invoice_file.open('rb')
    except (FileNotFoundError, IOError):
        raise Http404('Invoice file not found on disk')
    filename = os.path.basename(p.invoice_file.name)
    resp = FileResponse(f, as_attachment=True, filename=filename)
    return resp


@_crm_auth
@require_GET
def serve_evidence(request, pk):
    """GET /wi/crm/evidence/<pk>/file/ — serve EvidenceFile attachment."""
    e = get_object_or_404(EvidenceFile, pk=pk)
    if not e.file or not e.file.name:
        raise Http404('No file attached')
    try:
        f = e.file.open('rb')
    except (FileNotFoundError, IOError):
        raise Http404('Evidence file not found on disk')
    filename = os.path.basename(e.file.name)
    resp = FileResponse(f, as_attachment=True, filename=filename)
    return resp
