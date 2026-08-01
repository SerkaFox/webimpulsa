"""CRM services — lead creation, calculator data extraction, client portal.

Designed for extension:
  proposal_from_lead(lead)      → PDF/DOCX proposal generation
  client_portal_token(lead)     → signed URL for client portal
  invoice_from_lead(lead)       → invoice generation
  extranjeria_export(queryset)  → Extranjería CSV/XML export
"""
import hashlib
import io
import logging
import math
import os
import random
import secrets
import shutil
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from .models import ClientAccess, CommunicationLog, Lead, ProjectMaterial

logger = logging.getLogger(__name__)

_DISCOUNT  = 0.15
_RUSH_MULT = 1.25

def _js_round(x: float) -> int:
    """Round the same way JS Math.round does (half-up, not banker's rounding)."""
    return math.floor(x + 0.5)

_PORTAL_BASE_URL = os.getenv('WI_BASE_URL', 'https://creaganaweb.es')

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
        'hours_plan_name':     str(calc.get('hours_name') or '').strip()[:50],
        'hours_plan_price':    int(calc.get('hours') or 0),
        'hosting_price':       int(calc.get('hosting') or 0),
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
                "maint_name":   str,
                "hours":        int,
                "hours_name":   str,
                "hosting":      int
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
        WI_COMPANY, EXTRAS_PRICES, EXTRAS_DESCRIPTIONS, PROJECT_SCOPES, DEFAULT_SCOPE,
        OUT_OF_SCOPE, PHASES, CONDITIONS, DEADLINES,
    )

    purchased_extras = list(lead.extras or [])
    extras_with_prices = [
        {'name': name, 'price': EXTRAS_PRICES.get(name, 0)}
        for name in purchased_extras
    ]

    # Alcance = base package scope + a line per extra actually purchased, so the
    # document never claims to include something the client didn't pay for.
    scope_list = PROJECT_SCOPES.get(lead.package, DEFAULT_SCOPE)[:] + [
        EXTRAS_DESCRIPTIONS.get(name, name) for name in purchased_extras
    ]

    # No incluido = generic exclusions (minus hosting/domain if those were bought)
    # + every extra from the catalogue that was NOT purchased, named explicitly so
    # there's no ambiguity about what is/isn't part of this proposal.
    not_purchased_extras = [name for name in EXTRAS_PRICES if name not in purchased_extras]
    out_of_scope_list = [
        item for item in OUT_OF_SCOPE
        if not (lead.hosting_price and item in ('Compra de dominio', 'Hosting'))
    ] + [
        f'«{name}» (disponible como extra opcional, no incluido en este presupuesto)'
        for name in not_purchased_extras
    ]

    subtotal     = lead.package_base_price + lead.extras_price
    rush_amount  = _js_round(subtotal * 0.25) if lead.rush else 0
    if lead.rush:
        subtotal += rush_amount
    discount_amt = _js_round(subtotal * lead.discount_pct / 100)
    taxable_base = subtotal - discount_amt
    iva_amount   = _js_round(taxable_base * 0.21)
    total        = taxable_base + iva_amount

    # If the lead already has an accepted proposal, this new draft supersedes it —
    # any price/scope/timeline change must go through a fresh acceptance.
    previous_accepted = (
        lead.proposals.filter(status=Proposal.ST_ACCEPTED).order_by('-created_at').first()
    )

    proposal = Proposal.objects.create(
        number             = Proposal.generate_number(),
        lead               = lead,
        supersedes         = previous_accepted,
        issued_at          = timezone.localdate(),
        client_name        = lead.name,
        client_email       = lead.email,
        client_phone       = lead.phone,
        client_biz_type    = lead.biz_type,
        company_data       = WI_COMPANY.copy(),
        project_name       = lead.package or 'Proyecto web',
        scope              = scope_list,
        out_of_scope       = out_of_scope_list,
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
        hours_plan_name    = lead.hours_plan_name,
        hours_plan_price   = lead.hours_plan_price,
        hosting_price      = lead.hosting_price,
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
        'hoursPlanName':       proposal.hours_plan_name,
        'hoursPlanPrice':      proposal.hours_plan_price,
        'hostingPrice':        proposal.hosting_price,
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
            'tradeName': c.get('trade_name', 'CreaGanaWeb'),
            'legalName': c.get('legal_name', ''),
            'taxId':     c.get('nif', ''),
            'email':     c.get('email', 'info@creaganaweb.es'),
            'phone':     c.get('phone', ''),
            'website':   c.get('website', 'https://creaganaweb.es'),
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


# ── Client project file manager ───────────────────────────────────────────────
# Operates directly on the client's LIVE deployed project (Lead.project_path),
# by explicit choice — no snapshot indirection. The one non-negotiable guard is
# path traversal: every resolved path must stay inside project_path, and must
# never resolve into this CRM app's own codebase (a misconfigured project_path
# pointing at ourselves would otherwise let a client edit/delete our own app).

class ProjectFileError(Exception):
    pass


_OWN_BASE_DIR = Path(settings.BASE_DIR).resolve()

# Files small/simple enough to view and save as plain text in the browser.
# Anything else (images, archives, binaries, databases...) is download/delete
# only — editing them as text would corrupt them.
TEXT_EDIT_EXTENSIONS = {
    'html', 'htm', 'css', 'js', 'mjs', 'json', 'txt', 'md', 'py', 'xml',
    'yml', 'yaml', 'ini', 'cfg', 'conf', 'env', 'sh', 'csv', 'svg',
}
MAX_TEXT_EDIT_BYTES = 2 * 1024 * 1024  # 2 MB — generous for hand-written source files

# Dev-tooling / agent artifacts — never part of the actual deliverable site,
# irrelevant (or inappropriate) for the client to see. Hidden from both the
# browse listing and the full-project zip, at any depth.
HIDDEN_ENTRY_NAMES = {
    '.git', '.claude', '.codex', 'codex', '__pycache__',
    'venv', '.venv', 'node_modules', '.idea', '.vscode', '.DS_Store',
}


def _is_hidden(path: Path, root: Path) -> bool:
    return any(part in HIDDEN_ENTRY_NAMES for part in path.relative_to(root).parts)


def _project_root(lead: Lead) -> Path:
    if not lead.project_path:
        raise ProjectFileError('Este proyecto no tiene una carpeta configurada todavía.')
    root = Path(lead.project_path).resolve()
    if not root.is_dir():
        raise ProjectFileError('La carpeta del proyecto no existe en el servidor.')
    if root == _OWN_BASE_DIR or _OWN_BASE_DIR in root.parents or root in _OWN_BASE_DIR.parents:
        raise ProjectFileError('Ruta de proyecto no válida.')
    return root


def get_project_root(lead: Lead) -> Path:
    """Public wrapper around the same root-validation used by the file manager —
    used by the rolling-backup command so it shares the exact same safety checks."""
    return _project_root(lead)


def resolve_project_path(lead: Lead, rel_path: str = '') -> Path:
    """Resolve rel_path against the lead's project root, rejecting traversal
    and rejecting any hidden dev-tooling segment (.git, .claude, venv...) even
    if it's requested directly by URL rather than clicked from the listing."""
    root = _project_root(lead)
    candidate = (root / (rel_path or '').lstrip('/')).resolve()
    if candidate != root and root not in candidate.parents:
        raise ProjectFileError('Ruta fuera de la carpeta del proyecto.')
    if _is_hidden(candidate, root):
        raise ProjectFileError('Ese archivo no está disponible.')
    return candidate


def list_project_directory(lead: Lead, rel_path: str = '') -> dict:
    """Return {'root': bool-ish info, 'parent': str|None, 'entries': [...]}."""
    root = _project_root(lead)
    target = resolve_project_path(lead, rel_path)
    if not target.exists():
        raise ProjectFileError('Esa ruta ya no existe.')
    if not target.is_dir():
        raise ProjectFileError('Esa ruta no es una carpeta.')

    entries = []
    for child in sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
        if child.name in HIDDEN_ENTRY_NAMES:
            continue
        try:
            stat = child.stat()
        except OSError:
            continue
        child_rel = str(child.relative_to(root))
        ext = child.name.rsplit('.', 1)[-1].lower() if '.' in child.name else ''
        entries.append({
            'name': child.name,
            'rel_path': child_rel,
            'is_dir': child.is_dir(),
            'size': stat.st_size,
            'mtime': timezone.datetime.fromtimestamp(stat.st_mtime, tz=timezone.get_current_timezone()),
            'editable': (not child.is_dir()) and ext in TEXT_EDIT_EXTENSIONS and stat.st_size <= MAX_TEXT_EDIT_BYTES,
        })

    rel_norm = str(target.relative_to(root)) if target != root else ''
    parent_rel = None
    if target != root:
        parent_rel = str(target.parent.relative_to(root)) if target.parent != root else ''

    return {'rel_path': rel_norm, 'parent_rel': parent_rel, 'entries': entries}


def read_project_text_file(lead: Lead, rel_path: str) -> str:
    path = resolve_project_path(lead, rel_path)
    if not path.is_file():
        raise ProjectFileError('Ese archivo no existe.')
    ext = path.name.rsplit('.', 1)[-1].lower() if '.' in path.name else ''
    if ext not in TEXT_EDIT_EXTENSIONS:
        raise ProjectFileError('Este tipo de archivo no se puede editar como texto.')
    if path.stat().st_size > MAX_TEXT_EDIT_BYTES:
        raise ProjectFileError('El archivo es demasiado grande para editar aquí.')
    return path.read_text(encoding='utf-8', errors='replace')


def write_project_text_file(lead: Lead, rel_path: str, content: str) -> None:
    path = resolve_project_path(lead, rel_path)
    if path.is_dir():
        raise ProjectFileError('Ese nombre corresponde a una carpeta.')
    ext = path.name.rsplit('.', 1)[-1].lower() if '.' in path.name else ''
    if ext not in TEXT_EDIT_EXTENSIONS:
        raise ProjectFileError('Este tipo de archivo no se puede editar como texto.')
    path.write_text(content, encoding='utf-8')


def delete_project_path(lead: Lead, rel_path: str) -> None:
    root = _project_root(lead)
    path = resolve_project_path(lead, rel_path)
    if path == root:
        raise ProjectFileError('No se puede eliminar la carpeta raíz del proyecto.')
    if not path.exists():
        raise ProjectFileError('Esa ruta ya no existe.')
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()


def zip_project(lead: Lead) -> io.BytesIO:
    """Zip the entire live project folder (and project_db_path, if set and
    outside project_path) into an in-memory buffer for full-project download."""
    root = _project_root(lead)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for file_path in root.rglob('*'):
            if file_path.is_file() and not _is_hidden(file_path, root):
                zf.write(file_path, arcname=str(file_path.relative_to(root)))
        if lead.project_db_path:
            db_path = Path(lead.project_db_path).resolve()
            if db_path.is_file() and root not in db_path.parents:
                zf.write(db_path, arcname=f'database/{db_path.name}')
    buf.seek(0)
    return buf


def find_project_db_file(lead: Lead):
    """Best-effort auto-detect of a SQLite file inside the project folder, so
    Sergey doesn't have to separately browse for it after setting project_path.
    Prefers an exact 'db.sqlite3' match, then the shallowest '*.sqlite3'/'*.db'
    file found (skipping hidden/dev-tooling dirs). Returns None if nothing
    looks like a database — most static sites have none, and that's fine."""
    root = _project_root(lead)
    candidates = []
    for pattern in ('*.sqlite3', '*.db'):
        for path in root.rglob(pattern):
            if path.is_file() and not _is_hidden(path, root):
                candidates.append(path)
    if not candidates:
        return None
    exact = next((p for p in candidates if p.name == 'db.sqlite3'), None)
    if exact:
        return exact
    candidates.sort(key=lambda p: len(p.relative_to(root).parts))
    return candidates[0]


# ── Server folder picker (admin-only, CRM side) ───────────────────────────────
# Lets Sergey navigate the server's filesystem from the CRM instead of typing a
# path from memory. Scoped to /home/seradmin — every client project observed on
# this server lives somewhere under there; this is not the same trust boundary
# as the client-facing file manager above (this is gated by CRM login only).

_FS_BROWSE_ROOT = Path('/home/seradmin').resolve()


def list_server_directories(rel_path: str = '', include_files: bool = False) -> dict:
    """Admin-only server browser. By default lists directories only (for
    picking project_path); with include_files=True also lists files (for
    picking project_db_path — a specific file, not a folder)."""
    target = (_FS_BROWSE_ROOT / (rel_path or '').lstrip('/')).resolve()
    if target != _FS_BROWSE_ROOT and _FS_BROWSE_ROOT not in target.parents:
        raise ProjectFileError('Ruta fuera del área permitida.')
    if not target.is_dir():
        raise ProjectFileError('Esa ruta no es una carpeta.')

    entries = []
    try:
        children = sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    except PermissionError:
        children = []
    for child in children:
        if child.name.startswith('.') or child.name in HIDDEN_ENTRY_NAMES:
            continue
        is_dir = child.is_dir()
        if not is_dir and not include_files:
            continue
        if is_dir:
            try:
                next(child.iterdir(), None)  # permission probe, ignore actual contents
            except PermissionError:
                continue
        entries.append({
            'name': child.name,
            'rel_path': str(child.relative_to(_FS_BROWSE_ROOT)),
            'is_dir': is_dir,
        })

    rel_norm = str(target.relative_to(_FS_BROWSE_ROOT)) if target != _FS_BROWSE_ROOT else ''
    parent_rel = None
    if target != _FS_BROWSE_ROOT:
        parent_rel = (str(target.parent.relative_to(_FS_BROWSE_ROOT))
                      if target.parent != _FS_BROWSE_ROOT else '')

    return {
        'abs_path': str(target),
        'rel_path': rel_norm,
        'parent_rel': parent_rel,
        'entries': entries,
    }


# ── Backup (shared by the weekly cron command + the CRM "backup now" button) ──

def backup_lead_project(lead: Lead) -> Path:
    """Tar the lead's live project (+ DB, if configured separately) into
    media/client_backups/<lead_id>/snapshot_<timestamp>.tar.gz, then prune to
    the 3 most recent snapshots for that lead. Returns the new snapshot path."""
    import tarfile

    root = _project_root(lead)
    dest_dir = Path(settings.MEDIA_ROOT) / 'client_backups' / str(lead.pk)
    dest_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    snapshot_path = dest_dir / f'snapshot_{timestamp}.tar.gz'

    with tarfile.open(snapshot_path, 'w:gz') as tar:
        tar.add(root, arcname='project')
        if lead.project_db_path:
            db_path = Path(lead.project_db_path).resolve()
            if db_path.is_file() and root not in db_path.parents:
                tar.add(db_path, arcname=f'database/{db_path.name}')

    snapshots = sorted(dest_dir.glob('snapshot_*.tar.gz'), key=lambda p: p.name)
    for old in snapshots[:-3]:
        old.unlink()

    return snapshot_path


def list_lead_backups(lead: Lead) -> list:
    """Snapshots on disk for this lead, newest first — lets Sergey actually
    see/download what "Hacer backup ahora" produced, instead of it just
    happening invisibly on the server."""
    dest_dir = Path(settings.MEDIA_ROOT) / 'client_backups' / str(lead.pk)
    if not dest_dir.is_dir():
        return []
    snapshots = sorted(dest_dir.glob('snapshot_*.tar.gz'), key=lambda p: p.name, reverse=True)
    return [
        {'name': p.name, 'size': p.stat().st_size, 'mtime': datetime.fromtimestamp(p.stat().st_mtime)}
        for p in snapshots
    ]


def get_lead_backup_path(lead: Lead, filename: str) -> Path:
    """Resolve a snapshot filename for download — only ever matches a real
    file already listed by list_lead_backups (no path traversal surface,
    since it's checked against the actual directory listing, not built from
    the filename directly)."""
    dest_dir = Path(settings.MEDIA_ROOT) / 'client_backups' / str(lead.pk)
    candidate = dest_dir / filename
    if candidate.parent != dest_dir or not candidate.is_file() or not filename.startswith('snapshot_'):
        raise ProjectFileError('Ese backup no existe.')
    return candidate


# ── Read-only SQLite browser (client portal — view/export only, no writes) ────

_SQLITE_ROW_PAGE = 100


def _sqlite_db_path(lead: Lead) -> Path:
    if not lead.project_db_path:
        raise ProjectFileError('Este proyecto no tiene una base de datos configurada.')
    path = Path(lead.project_db_path).resolve()
    if not path.is_file():
        raise ProjectFileError('El archivo de base de datos no existe en el servidor.')
    return path


def get_sqlite_db_path(lead: Lead) -> Path:
    """Public wrapper — used by the portal's raw-file-download endpoint."""
    return _sqlite_db_path(lead)


def list_sqlite_tables(lead: Lead) -> list:
    import sqlite3
    path = _sqlite_db_path(lead)
    con = sqlite3.connect(f'file:{path}?mode=ro', uri=True)
    try:
        cur = con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
        return [row[0] for row in cur.fetchall()]
    finally:
        con.close()


def read_sqlite_table(lead: Lead, table_name: str, offset: int = 0) -> dict:
    """Read-only, paginated row browse. table_name is whitelisted against the
    real table list before ever touching the query, so it can't be used to
    inject arbitrary SQL even though it comes from a URL param."""
    import sqlite3
    path = _sqlite_db_path(lead)
    tables = list_sqlite_tables(lead)
    if table_name not in tables:
        raise ProjectFileError('Esa tabla no existe.')

    con = sqlite3.connect(f'file:{path}?mode=ro', uri=True)
    try:
        total = con.execute(f'SELECT COUNT(*) FROM "{table_name}"').fetchone()[0]
        cur = con.execute(f'SELECT * FROM "{table_name}" LIMIT ? OFFSET ?', (_SQLITE_ROW_PAGE, offset))
        columns = [d[0] for d in cur.description]
        rows = cur.fetchall()
        return {
            'columns': columns, 'rows': rows, 'total': total,
            'offset': offset, 'end': offset + len(rows), 'page_size': _SQLITE_ROW_PAGE,
        }
    finally:
        con.close()
