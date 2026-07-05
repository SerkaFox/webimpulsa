"""CRM services — lead creation, calculator data extraction, client portal.

Designed for extension:
  proposal_from_lead(lead)      → PDF/DOCX proposal generation
  client_portal_token(lead)     → signed URL for client portal
  invoice_from_lead(lead)       → invoice generation
  extranjeria_export(queryset)  → Extranjería CSV/XML export
"""
import hashlib
import logging
import math
import os
import random
import secrets
from datetime import timedelta

from django.utils import timezone

from .models import ClientAccess, CommunicationLog, Lead, ProjectMaterial

logger = logging.getLogger(__name__)

_DISCOUNT  = 0.15
_RUSH_MULT = 1.25

def _js_round(x: float) -> int:
    """Round the same way JS Math.round does (half-up, not banker's rounding)."""
    return math.floor(x + 0.5)

_PORTAL_BASE_URL = os.getenv('WI_BASE_URL', 'https://webimpulsa.es')

# ── Lead creation ─────────────────────────────────────────────────────────────

def extract_calc_data(payload: dict) -> dict:
    """Parse and validate calculator fields from the raw API payload."""
    calc        = payload.get('calc') or {}
    base        = int(calc.get('base') or 0)
    extras_price = int(calc.get('extras_price') or 0)
    rush        = bool(calc.get('rush', False))

    subtotal = base + extras_price
    if rush:
        subtotal = _js_round(subtotal * _RUSH_MULT)
    discount = _js_round(subtotal * _DISCOUNT)
    total    = subtotal - discount

    return {
        'package':             str(calc.get('package') or '').strip()[:100],
        'package_base_price':  base,
        'extras':              [str(e) for e in (calc.get('extras') or [])],
        'extras_price':        extras_price,
        'rush':                rush,
        'maintenance_plan':    str(calc.get('maint_name') or '').strip()[:50],
        'maintenance_price':   int(calc.get('maint') or 0),
        'estimated_price':     total,
        'discount_pct':        15,
    }


def lead_from_payload(payload: dict) -> Lead:
    """Create and persist a Lead from a calculator submission payload.

    Expected payload structure::

        {
            "name":     str,      # required
            "contact":  str,      # required — phone or email
            "biz_type": str,      # optional
            "source":   str,      # optional, default "calculator"
            "calc": {
                "package":      str,
                "base":         int,
                "extras":       [str, ...],
                "extras_price": int,
                "rush":         bool,
                "maint":        int,
                "maint_name":   str
            }
        }
    """
    name     = str(payload.get('name')     or '').strip()[:200]
    contact  = str(payload.get('contact')  or '').strip()
    biz_type = str(payload.get('biz_type') or '').strip()[:100]
    source   = str(payload.get('source')   or Lead.SRC_CALCULATOR)

    email = contact if '@' in contact else ''
    phone = contact if '@' not in contact else ''

    return Lead.objects.create(
        name=name,
        email=email,
        phone=phone,
        biz_type=biz_type,
        source=source,
        raw_data=payload,
        **extract_calc_data(payload),
    )


# ── Client portal access ──────────────────────────────────────────────────────

def generate_client_access(
    lead: Lead,
    expires_hours: int = 72,
    pin_required: bool = True,
) -> tuple[ClientAccess, str, str | None]:
    """Create a new magic-link token for the client portal.

    Deactivates any existing active tokens for this lead first.

    Returns:
        (access, portal_url, pin_plaintext)
        pin_plaintext is None when pin_required=False
    """
    # Invalidate existing tokens
    ClientAccess.objects.filter(lead=lead, is_active=True).update(is_active=False)

    token    = secrets.token_urlsafe(32)
    pin      = None
    pin_hash = ''

    if pin_required:
        pin      = str(random.randint(100000, 999999))
        pin_hash = hashlib.sha256(pin.encode()).hexdigest()

    access = ClientAccess.objects.create(
        lead=lead,
        token=token,
        pin_hash=pin_hash,
        pin_required=pin_required,
        expires_at=timezone.now() + timedelta(hours=expires_hours),
    )

    portal_url = f'{_PORTAL_BASE_URL}/p/{token}/'

    log_communication(
        lead=lead,
        direction=CommunicationLog.DIR_OUTBOUND,
        channel=CommunicationLog.CH_PORTAL,
        content=f'Enlace de acceso generado (token {token[:8]}…). Expira en {expires_hours}h.',
        status=CommunicationLog.ST_SENT,
    )

    logger.info('Client access generated: lead #%d token=%s… pin_required=%s',
                lead.pk, token[:8], pin_required)
    return access, portal_url, pin


def validate_portal_token(token: str) -> ClientAccess | None:
    """Return a valid, non-expired ClientAccess or None."""
    try:
        access = ClientAccess.objects.select_related('lead').get(token=token)
    except ClientAccess.DoesNotExist:
        return None
    if not access.is_valid:
        return None
    return access


def expire_client_access(lead: Lead) -> int:
    """Deactivate all active tokens for a lead.  Returns count deactivated."""
    return ClientAccess.objects.filter(lead=lead, is_active=True).update(is_active=False)


def record_portal_visit(access: ClientAccess) -> None:
    """Update last_access and increment counter on a successful portal load."""
    access.last_access = timezone.now()
    access.access_count += 1
    access.save(update_fields=['last_access', 'access_count'])


# A poll within this window counts as "currently online" — mirrors the admin-side
# _ADMIN_ONLINE_WINDOW in views_portal.py.
CLIENT_ONLINE_WINDOW = 20  # seconds


def client_presence(lead: Lead):
    """Return (is_online, last_seen) for the client, based on ClientAccess.last_access,
    which is bumped on every client /messages/ poll while the portal chat is open."""
    access = lead.access_tokens.filter(is_active=True).order_by('-created_at').first()
    last_seen = access.last_access if access else None
    online = bool(last_seen and (timezone.now() - last_seen).total_seconds() < CLIENT_ONLINE_WINDOW)
    return online, last_seen


# ── Communication logging ─────────────────────────────────────────────────────

def log_communication(
    lead: Lead,
    direction: str,
    channel: str,
    content: str,
    template_name: str = '',
    status: str = CommunicationLog.ST_SENT,
    wamid: str = '',
    notes: str = '',
) -> CommunicationLog:
    """Create a CommunicationLog entry."""
    return CommunicationLog.objects.create(
        lead=lead,
        direction=direction,
        channel=channel,
        content=content,
        template_name=template_name,
        status=status,
        wamid=wamid,
        notes=notes,
    )


# ── Material handling ─────────────────────────────────────────────────────────

MAX_UPLOAD_BYTES = 15 * 1024 * 1024  # 15 MB per file

_ALLOWED_EXTENSIONS = {
    # images
    'jpg', 'jpeg', 'png', 'gif', 'webp', 'heic', 'heif', 'bmp', 'tiff',
    # video
    'mp4', 'mov', 'avi', 'mkv', 'webm', 'm4v',
    # design
    'svg', 'ai', 'eps', 'psd',
    # documents
    'pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx',
    # text
    'txt', 'rtf', 'md', 'csv',
}


def save_material(
    lead: Lead,
    uploaded_file,
    source: str = ProjectMaterial.SRC_PORTAL,
    notes: str = '',
    uploaded_by: str = '',
) -> ProjectMaterial | str:
    """Validate and save an uploaded file.  Returns ProjectMaterial or error string."""
    original_name = uploaded_file.name or 'archivo'
    ext = original_name.rsplit('.', 1)[-1].lower() if '.' in original_name else ''

    if ext not in _ALLOWED_EXTENSIONS:
        return f'Tipo de archivo no permitido: .{ext}'

    if uploaded_file.size > MAX_UPLOAD_BYTES:
        return f'El archivo supera el límite de {MAX_UPLOAD_BYTES // 1024 // 1024} MB'

    file_type = ProjectMaterial.type_from_filename(original_name)

    material = ProjectMaterial.objects.create(
        lead=lead,
        file=uploaded_file,
        original_filename=original_name,
        file_type=file_type,
        file_size=uploaded_file.size,
        source=source,
        notes=notes,
        uploaded_by_name=uploaded_by,
    )

    log_communication(
        lead=lead,
        direction=CommunicationLog.DIR_INBOUND,
        channel=CommunicationLog.CH_PORTAL,
        content=f'Material subido: {original_name} ({material.size_display})',
        status=CommunicationLog.ST_DELIVERED,
    )

    logger.info('Material saved: lead #%d file=%s size=%d',
                lead.pk, original_name, uploaded_file.size)
    return material


# ── Proposal services ─────────────────────────────────────────────────────────

def create_proposal_from_lead(lead: Lead):
    """Create a draft Proposal pre-populated from Lead calculator data."""
    from .models import Proposal
    from .proposal_content import (
        WI_COMPANY, EXTRAS_PRICES, PROJECT_SCOPES, DEFAULT_SCOPE,
        OUT_OF_SCOPE, PHASES, CONDITIONS, DEADLINES,
    )

    extras_with_prices = [
        {'name': name, 'price': EXTRAS_PRICES.get(name, 0)}
        for name in (lead.extras or [])
    ]

    subtotal     = lead.package_base_price + lead.extras_price
    rush_amount  = _js_round(subtotal * 0.25) if lead.rush else 0
    if lead.rush:
        subtotal += rush_amount
    discount_amt = _js_round(subtotal * lead.discount_pct / 100)
    taxable_base = subtotal - discount_amt
    iva_amount   = _js_round(taxable_base * 0.21)
    total        = taxable_base + iva_amount

    proposal = Proposal.objects.create(
        number             = Proposal.generate_number(),
        lead               = lead,
        issued_at          = timezone.localdate(),
        client_name        = lead.name,
        client_email       = lead.email,
        client_phone       = lead.phone,
        client_biz_type    = lead.biz_type,
        company_data       = WI_COMPANY.copy(),
        project_name       = lead.package or 'Proyecto web',
        scope              = PROJECT_SCOPES.get(lead.package, DEFAULT_SCOPE)[:],
        out_of_scope       = OUT_OF_SCOPE[:],
        phases             = PHASES[:],
        conditions         = CONDITIONS[:],
        timeline           = DEADLINES.get(lead.package, 'Según alcance'),
        payment_method     = '50-50',
        package            = lead.package,
        package_base_price = lead.package_base_price,
        extras             = extras_with_prices,
        extras_price       = lead.extras_price,
        rush               = lead.rush,
        rush_amount        = rush_amount,
        discount_pct       = lead.discount_pct,
        discount_amount    = discount_amt,
        taxable_base       = taxable_base,
        iva_amount         = iva_amount,
        total_with_iva     = total,
        maintenance_plan   = lead.maintenance_plan,
        maintenance_price  = lead.maintenance_price,
    )

    log_communication(
        lead=lead,
        direction=CommunicationLog.DIR_OUTBOUND,
        channel=CommunicationLog.CH_MANUAL,
        content=f'Propuesta {proposal.number} creada (borrador).',
        status=CommunicationLog.ST_PENDING,
    )
    return proposal


def proposal_to_template_input(proposal) -> dict:
    """Convert a Proposal to the input dict for WIProposalTemplate.buildProposalData()."""
    c = proposal.company_data or {}
    return {
        'projectType':         proposal.package or 'Proyecto a medida',
        'basePrice':           proposal.package_base_price,
        'extras':              proposal.extras or [],
        'extrasTotal':         proposal.extras_price,
        'rushAmount':          proposal.rush_amount,
        'discountAmount':      proposal.discount_amount,
        'maintenanceName':     proposal.maintenance_plan,
        'maintenancePrice':    proposal.maintenance_price,
        'maintenanceInfo':     '',
        'budgetNumber':        proposal.number,
        'issueDate':           proposal.issued_at.strftime('%Y-%m-%d') if proposal.issued_at else '',
        'validDays':           proposal.valid_days,
        'client': {
            'name':          proposal.client_name,
            'taxId':         proposal.client_nif,
            'contactPerson': proposal.client_name,
            'email':         proposal.client_email,
            'phone':         proposal.client_phone,
            'address':       proposal.client_address,
            'city':          proposal.client_city,
            'businessType':  proposal.client_biz_type,
        },
        'projectName':         proposal.project_name,
        'goal':                proposal.project_goal,
        'businessDescription': proposal.biz_description,
        'selectedFeatures':    proposal.selected_features,
        'deadline':            proposal.timeline,
        'startDate':           proposal.start_date,
        'notes':               proposal.notes,
        'paymentMethod':       proposal.payment_method,
        'customPayment':       proposal.payment_custom,
        'company': {
            'tradeName': c.get('trade_name', 'WebImpulsa'),
            'legalName': c.get('legal_name', ''),
            'taxId':     c.get('nif', ''),
            'email':     c.get('email', 'info@webimpulsa.es'),
            'phone':     c.get('phone', ''),
            'website':   c.get('website', 'https://webimpulsa.es'),
            'address':   c.get('address', ''),
            'logoUrl':   c.get('logo_url', '/static/wi/img/logo.webp'),
        },
    }


def mark_proposal_sent(proposal) -> None:
    """Mark proposal as sent and update lead status to propuesta_enviada."""
    proposal.status = proposal.ST_SENT
    proposal.save(update_fields=['status', 'updated_at'])

    lead = proposal.lead
    if lead.status in (Lead.ST_NUEVO, Lead.ST_CONTACTADO):
        lead.status = Lead.ST_PROPUESTA
        lead.save(update_fields=['status', 'updated_at'])

    log_communication(
        lead=lead,
        direction=CommunicationLog.DIR_OUTBOUND,
        channel=CommunicationLog.CH_PORTAL,
        content=f'Propuesta {proposal.number} marcada como enviada al cliente.',
        status=CommunicationLog.ST_SENT,
    )


PAYMENT_PLAN_CHOICES = [
    ('full',  'Pago único'),
    ('50-50', '50% ahora + 50% a la entrega'),
    ('3-way', '3 pagos (33% cada uno)'),
]
_PAYMENT_PLAN_CODES = {code for code, _ in PAYMENT_PLAN_CHOICES}


def payment_schedule(proposal) -> dict:
    """Return {first_amount, first_label, schedule_text} for the proposal's payment_method."""
    total = proposal.total_with_iva
    plan  = proposal.payment_method if proposal.payment_method in _PAYMENT_PLAN_CODES else '50-50'

    if plan == 'full':
        return {
            'plan': plan,
            'first_amount': total,
            'first_label': 'Pago único',
            'schedule_text': 'Pago completo — sin más pagos pendientes.',
        }
    if plan == '3-way':
        third = total // 3
        return {
            'plan': plan,
            'first_amount': third,
            'first_label': 'Primer pago (1 de 3)',
            'schedule_text': f'3 pagos de {third}€: ahora, al 50% del proyecto y a la entrega.',
        }
    # default '50-50'
    half = total // 2
    return {
        'plan': plan,
        'first_amount': half,
        'first_label': 'Primer pago (50%)',
        'schedule_text': f'Segundo pago de {total - half}€ a la entrega.',
    }


def serialize_chat_message(m) -> dict:
    """Shared JSON shape for portal-channel chat messages (client portal + CRM admin)."""
    reply_snippet = None
    if m.reply_to_id and m.reply_to:
        reply_snippet = {
            'id': m.reply_to_id,
            'content': (m.reply_to.content[:120] if not m.reply_to.deleted else 'Mensaje eliminado'),
            'direction': m.reply_to.direction,
        }
    return {
        'id':        m.pk,
        'direction': m.direction,
        'content':   ('Mensaje eliminado' if m.deleted else m.content),
        'deleted':   m.deleted,
        'created_at': m.created_at.isoformat(),
        'read_at':    m.read_at.isoformat() if m.read_at else None,
        'reactions':  m.reactions or [],
        'reply_to':   reply_snippet,
    }


def accept_proposal(proposal, name: str, nif: str, signature: str) -> None:
    """Record client acceptance: update proposal + lead status + log."""
    proposal.status             = proposal.ST_ACCEPTED
    proposal.accepted_by_name   = name[:200]
    proposal.accepted_nif       = nif[:30]
    proposal.accepted_signature = signature[:200]
    proposal.accepted_at        = timezone.now()
    proposal.save(update_fields=[
        'status', 'accepted_by_name', 'accepted_nif',
        'accepted_signature', 'accepted_at', 'updated_at',
    ])

    lead = proposal.lead
    if lead.status not in (Lead.ST_ACEPTADO, Lead.ST_EN_TRABAJO, Lead.ST_FINALIZADO):
        lead.status = Lead.ST_ACEPTADO
        lead.save(update_fields=['status', 'updated_at'])

    log_communication(
        lead=lead,
        direction=CommunicationLog.DIR_INBOUND,
        channel=CommunicationLog.CH_PORTAL,
        content=f'Propuesta {proposal.number} aceptada por {name} (NIF: {nif or "—"}).',
        status=CommunicationLog.ST_DELIVERED,
    )


def compose_proposal_wa_message(proposal, portal_url: str) -> str:
    """Compose a WhatsApp message announcing the proposal is ready."""
    first = (proposal.client_name or 'cliente').split()[0]
    return (
        f'Hola {first} 👋\n\n'
        f'Tu propuesta de proyecto está lista para revisar.\n\n'
        f'📋 *{proposal.number}*\n'
        f'Proyecto: {proposal.package}\n'
        f'Total (IVA incluido): *{proposal.total_with_iva}€*\n\n'
        f'Revísala y acéptala aquí:\n'
        f'🔗 {portal_url}\n\n'
        f'Validez: {proposal.valid_days} días naturales.\n'
        f'¿Alguna pregunta? Escríbenos 😊'
    )


# ── Status → next-step mapping ────────────────────────────────────────────────

NEXT_STEPS = {
    Lead.ST_NUEVO:        'Contactar al cliente para conocer sus necesidades.',
    Lead.ST_CONTACTADO:   'Preparar y enviar la propuesta de proyecto.',
    Lead.ST_PROPUESTA:    'Esperar respuesta del cliente · hacer seguimiento en 48h.',
    Lead.ST_NEGOCIACION:  'Cerrar los términos finales y confirmar el presupuesto.',
    Lead.ST_ACEPTADO:     'Solicitar materiales al cliente y acordar fecha de inicio.',
    Lead.ST_EN_TRABAJO:   'Proyecto en desarrollo · informar al cliente del avance.',
    Lead.ST_FINALIZADO:   'Solicitar valoración y testimonial al cliente.',
    Lead.ST_PERDIDO:      '—',
}

CLIENT_STATUS_LABEL = {
    Lead.ST_NUEVO:        'Recibido',
    Lead.ST_CONTACTADO:   'En contacto',
    Lead.ST_PROPUESTA:    'Propuesta enviada',
    Lead.ST_NEGOCIACION:  'En negociación',
    Lead.ST_ACEPTADO:     'Aceptado ✓',
    Lead.ST_EN_TRABAJO:   'En desarrollo 🚧',
    Lead.ST_FINALIZADO:   'Completado ✅',
    Lead.ST_PERDIDO:      'Cerrado',
}

CLIENT_NEXT_STEP = {
    Lead.ST_NUEVO:        'Nos ponemos en contacto contigo próximamente.',
    Lead.ST_CONTACTADO:   'Estamos preparando tu propuesta personalizada.',
    Lead.ST_PROPUESTA:    'Revisa la propuesta y coméntanos cualquier ajuste.',
    Lead.ST_NEGOCIACION:  'Estamos ultimando los detalles de tu proyecto.',
    Lead.ST_ACEPTADO:     'Por favor, sube los materiales de tu proyecto para comenzar.',
    Lead.ST_EN_TRABAJO:   'Tu proyecto está en desarrollo. Te avisamos en cada avance.',
    Lead.ST_FINALIZADO:   '¡Tu proyecto está publicado! Cuéntanos cómo podemos seguir ayudándote.',
    Lead.ST_PERDIDO:      'Gracias por considerarnos. Puedes volver cuando lo necesites.',
}

# Fallback progress (%) by pipeline stage, used when a lead has no explicit
# milestones yet. ST_PERDIDO is intentionally absent — no progress bar for closed leads.
CLIENT_STAGE_PROGRESS = {
    Lead.ST_NUEVO:        5,
    Lead.ST_CONTACTADO:   15,
    Lead.ST_PROPUESTA:    30,
    Lead.ST_NEGOCIACION:  40,
    Lead.ST_ACEPTADO:     55,
    Lead.ST_EN_TRABAJO:   75,
    Lead.ST_FINALIZADO:   100,
}
