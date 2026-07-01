"""CRM services — lead creation, calculator data extraction, client portal.

Designed for extension:
  proposal_from_lead(lead)      → PDF/DOCX proposal generation
  client_portal_token(lead)     → signed URL for client portal
  invoice_from_lead(lead)       → invoice generation
  extranjeria_export(queryset)  → Extranjería CSV/XML export
"""
import hashlib
import logging
import os
import random
import secrets
from datetime import timedelta

from django.utils import timezone

from .models import ClientAccess, CommunicationLog, Lead, ProjectMaterial

logger = logging.getLogger(__name__)

_DISCOUNT  = 0.15
_RUSH_MULT = 1.25

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
        subtotal = round(subtotal * _RUSH_MULT)
    discount = round(subtotal * _DISCOUNT)
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
