import hashlib
import math
import os
from datetime import timedelta

from django.db import models
from django.utils import timezone


class Lead(models.Model):
    # ── statuses ──────────────────────────────────────────────────────────────
    ST_NUEVO            = 'nuevo'
    ST_CONTACTADO       = 'contactado'
    ST_PROPUESTA        = 'propuesta_enviada'
    ST_NEGOCIACION      = 'negociacion'
    ST_ACEPTADO         = 'aceptado'
    ST_EN_TRABAJO       = 'en_trabajo'
    ST_FINALIZADO       = 'finalizado'
    ST_PERDIDO          = 'perdido'

    STATUS_CHOICES = [
        (ST_NUEVO,       'Nuevo'),
        (ST_CONTACTADO,  'Contactado'),
        (ST_PROPUESTA,   'Propuesta enviada'),
        (ST_NEGOCIACION, 'Negociación'),
        (ST_ACEPTADO,    'Aceptado'),
        (ST_EN_TRABAJO,  'En trabajo'),
        (ST_FINALIZADO,  'Finalizado'),
        (ST_PERDIDO,     'Perdido'),
    ]

    # ── sources ───────────────────────────────────────────────────────────────
    SRC_CALCULATOR = 'calculator'
    SRC_CONTACT    = 'contact_form'
    SRC_CHAT       = 'chat'
    SRC_WHATSAPP   = 'whatsapp'
    SRC_MANUAL     = 'manual'

    SOURCE_CHOICES = [
        (SRC_CALCULATOR, 'Calculadora'),
        (SRC_CONTACT,    'Formulario de contacto'),
        (SRC_CHAT,       'Chat en vivo'),
        (SRC_WHATSAPP,   'WhatsApp'),
        (SRC_MANUAL,     'Manual'),
    ]

    # ── preferred channel ─────────────────────────────────────────────────────
    CH_WHATSAPP = 'whatsapp'
    CH_EMAIL    = 'email'
    CH_BOTH     = 'both'

    CHANNEL_CHOICES = [
        (CH_WHATSAPP, 'WhatsApp'),
        (CH_EMAIL,    'Email'),
        (CH_BOTH,     'WhatsApp + Email'),
    ]

    # ── client data ───────────────────────────────────────────────────────────
    name              = models.CharField(max_length=200)
    email             = models.CharField(max_length=200, blank=True)
    phone             = models.CharField(max_length=50, blank=True)
    biz_type          = models.CharField(max_length=100, blank=True)
    preferred_channel = models.CharField(max_length=20, choices=CHANNEL_CHOICES, default=CH_WHATSAPP)

    # ── package / calculator data ─────────────────────────────────────────────
    package            = models.CharField(max_length=100, blank=True)
    package_base_price = models.IntegerField(default=0)
    extras             = models.JSONField(default=list)
    extras_price       = models.IntegerField(default=0)
    rush               = models.BooleanField(default=False)
    maintenance_plan   = models.CharField(max_length=50, blank=True)
    maintenance_price  = models.IntegerField(default=0)
    estimated_price    = models.IntegerField(default=0)
    discount_pct       = models.IntegerField(default=15)

    # ── CRM fields ────────────────────────────────────────────────────────────
    source   = models.CharField(max_length=30, choices=SOURCE_CHOICES, default=SRC_CALCULATOR)
    status   = models.CharField(max_length=30, choices=STATUS_CHOICES, default=ST_NUEVO)
    notes    = models.TextField(blank=True)
    raw_data = models.JSONField(default=dict)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Bumped each time the admin chat widget polls for this lead — used to
    # detect "Tatiana currently has this lead open" and skip WA/TG duplicate pings.
    admin_chat_seen_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Lead #{self.pk} — {self.name} ({self.package or "—"})'

    @property
    def contact(self):
        return self.email or self.phone


# ── CLIENT ACCESS ──────────────────────────────────────────────────────────────

class ClientAccess(models.Model):
    """Magic-link token + optional PIN for client portal access.

    One active token per lead at a time.  Older tokens are deactivated when
    a new one is generated.  Tokens carry a 72-hour TTL by default.

    Security model:
      - Token: 32-byte URL-safe random → 256-bit entropy, brute-force infeasible
      - PIN:   6-digit, stored as SHA-256 hex; expires with token
      - Session verification stored in Django's signed cookie session
    """
    lead        = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name='access_tokens')
    token       = models.CharField(max_length=64, unique=True, db_index=True)
    pin_hash    = models.CharField(max_length=128, blank=True)  # SHA-256 hex
    pin_required = models.BooleanField(default=True)
    expires_at  = models.DateTimeField()
    last_access = models.DateTimeField(null=True, blank=True)
    access_count = models.IntegerField(default=0)
    is_active   = models.BooleanField(default=True)
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Access for Lead #{self.lead_id} — {self.token[:12]}...'

    @property
    def is_expired(self):
        return timezone.now() > self.expires_at

    @property
    def is_valid(self):
        return self.is_active and not self.is_expired

    def check_pin(self, pin: str) -> bool:
        if not self.pin_required or not self.pin_hash:
            return True
        return hashlib.sha256(pin.encode()).hexdigest() == self.pin_hash

    def portal_url(self, base_url: str = 'https://webimpulsa.es') -> str:
        return f'{base_url}/p/{self.token}/'


# ── COMMUNICATION LOG ──────────────────────────────────────────────────────────

class CommunicationLog(models.Model):
    """Audit trail for all outbound/inbound communications per lead.

    Supports WhatsApp, email, portal messages and manual log entries.
    """
    DIR_OUTBOUND = 'outbound'
    DIR_INBOUND  = 'inbound'

    CH_WHATSAPP = 'whatsapp'
    CH_EMAIL    = 'email'
    CH_PORTAL   = 'portal'
    CH_MANUAL   = 'manual'

    ST_PENDING   = 'pending'
    ST_SENT      = 'sent'
    ST_DELIVERED = 'delivered'
    ST_READ      = 'read'
    ST_FAILED    = 'failed'

    DIRECTION_CHOICES = [
        (DIR_OUTBOUND, 'Saliente'),
        (DIR_INBOUND,  'Entrante'),
    ]
    CHANNEL_CHOICES = [
        (CH_WHATSAPP, 'WhatsApp'),
        (CH_EMAIL,    'Email'),
        (CH_PORTAL,   'Portal'),
        (CH_MANUAL,   'Manual'),
    ]
    STATUS_CHOICES = [
        (ST_PENDING,   'Pendiente'),
        (ST_SENT,      'Enviado'),
        (ST_DELIVERED, 'Entregado'),
        (ST_READ,      'Leído'),
        (ST_FAILED,    'Fallido'),
    ]

    lead          = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name='comm_log')
    direction     = models.CharField(max_length=10, choices=DIRECTION_CHOICES)
    channel       = models.CharField(max_length=20, choices=CHANNEL_CHOICES)
    template_name = models.CharField(max_length=100, blank=True)
    content       = models.TextField()
    status        = models.CharField(max_length=20, choices=STATUS_CHOICES, default=ST_SENT)
    wamid         = models.CharField(max_length=256, blank=True)  # WhatsApp message ID
    notes         = models.TextField(blank=True)
    delivered_at  = models.DateTimeField(null=True, blank=True)
    created_at    = models.DateTimeField(auto_now_add=True)

    # Portal chat extras (only meaningful for channel=portal)
    reply_to  = models.ForeignKey('self', null=True, blank=True,
                                   on_delete=models.SET_NULL, related_name='replies')
    reactions = models.JSONField(default=list, blank=True)   # [{"emoji": "❤️", "by": "client"|"team"}]
    deleted   = models.BooleanField(default=False)
    read_at   = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'[{self.direction}/{self.channel}] Lead #{self.lead_id} — {self.content[:60]}'


# ── PROJECT MATERIALS ──────────────────────────────────────────────────────────

def _material_upload_path(instance, filename):
    safe = ''.join(c for c in filename if c.isalnum() or c in '._- ').rstrip()
    return f'materials/{instance.lead_id}/{safe}'


class ProjectMaterial(models.Model):
    """File uploaded by client or team for a project.

    Files are stored in MEDIA_ROOT/materials/{lead_id}/ and served through
    a protected Django view — not directly accessible via Nginx.

    Future: virus scan hook, image thumbnail generation, cloud storage backend.
    """
    TYPE_PHOTO    = 'photo'
    TYPE_VIDEO    = 'video'
    TYPE_LOGO     = 'logo'
    TYPE_TEXT     = 'text'
    TYPE_DOCUMENT = 'document'
    TYPE_OTHER    = 'other'

    SRC_PORTAL    = 'portal'
    SRC_WHATSAPP  = 'whatsapp'
    SRC_EMAIL     = 'email'
    SRC_MANUAL    = 'manual'

    TYPE_CHOICES = [
        (TYPE_PHOTO,    'Foto'),
        (TYPE_VIDEO,    'Video'),
        (TYPE_LOGO,     'Logo / imagen corporativa'),
        (TYPE_TEXT,     'Texto / contenido'),
        (TYPE_DOCUMENT, 'Documento'),
        (TYPE_OTHER,    'Otro'),
    ]
    SOURCE_CHOICES = [
        (SRC_PORTAL,   'Portal cliente'),
        (SRC_WHATSAPP, 'WhatsApp'),
        (SRC_EMAIL,    'Email'),
        (SRC_MANUAL,   'Subida manualmente'),
    ]

    # Image extensions
    _IMG_EXTS = {'jpg', 'jpeg', 'png', 'gif', 'webp', 'heic', 'heif', 'bmp', 'tiff'}
    _VID_EXTS = {'mp4', 'mov', 'avi', 'mkv', 'webm', 'm4v'}
    _LOGO_EXTS = {'svg', 'ai', 'eps', 'psd', 'pdf'}
    _TXT_EXTS = {'txt', 'rtf', 'md', 'csv'}
    _DOC_EXTS = {'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx'}

    lead              = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name='materials')
    file              = models.FileField(upload_to=_material_upload_path)
    original_filename = models.CharField(max_length=255)
    file_type         = models.CharField(max_length=20, choices=TYPE_CHOICES, default=TYPE_OTHER)
    file_size         = models.IntegerField(default=0)   # bytes
    source            = models.CharField(max_length=20, choices=SOURCE_CHOICES, default=SRC_PORTAL)
    notes             = models.TextField(blank=True)
    uploaded_by_name  = models.CharField(max_length=200, blank=True)
    created_at        = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.original_filename} (Lead #{self.lead_id})'

    @property
    def size_display(self):
        kb = self.file_size / 1024
        if kb < 1024:
            return f'{kb:.0f} KB'
        return f'{kb / 1024:.1f} MB'

    @classmethod
    def type_from_filename(cls, filename: str) -> str:
        ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
        if ext in cls._IMG_EXTS:
            return cls.TYPE_PHOTO
        if ext in cls._VID_EXTS:
            return cls.TYPE_VIDEO
        if ext in cls._LOGO_EXTS:
            return cls.TYPE_LOGO
        if ext in cls._TXT_EXTS:
            return cls.TYPE_TEXT
        if ext in cls._DOC_EXTS:
            return cls.TYPE_DOCUMENT
        return cls.TYPE_OTHER


# ── PROPOSALS ──────────────────────────────────────────────────────────────────

class Proposal(models.Model):
    """Professional proposal/budget tied to a Lead.

    Number format: WI-YYYYMMDD-XXXX (sequential per day).
    Client-visible statuses: sent, viewed, accepted.
    Pricing fields are a snapshot from the Lead calculator but fully editable.
    scope/out_of_scope/phases/conditions are stored so they survive editing.
    """
    ST_DRAFT    = 'draft'
    ST_SENT     = 'sent'
    ST_VIEWED   = 'viewed'
    ST_ACCEPTED = 'accepted'
    ST_REJECTED = 'rejected'
    ST_EXPIRED  = 'expired'

    STATUS_CHOICES = [
        (ST_DRAFT,    'Borrador'),
        (ST_SENT,     'Enviada'),
        (ST_VIEWED,   'Vista'),
        (ST_ACCEPTED, 'Aceptada'),
        (ST_REJECTED, 'Rechazada'),
        (ST_EXPIRED,  'Expirada'),
    ]

    # Identity
    number     = models.CharField(max_length=30, unique=True)
    lead       = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name='proposals')
    status     = models.CharField(max_length=20, choices=STATUS_CHOICES, default=ST_DRAFT)
    valid_days = models.IntegerField(default=15)
    issued_at  = models.DateField()

    # Client data snapshot (editable)
    client_name     = models.CharField(max_length=200, blank=True)
    client_email    = models.CharField(max_length=200, blank=True)
    client_phone    = models.CharField(max_length=50, blank=True)
    client_biz_type = models.CharField(max_length=100, blank=True)
    client_nif      = models.CharField(max_length=30, blank=True)
    client_address  = models.CharField(max_length=300, blank=True)
    client_city     = models.CharField(max_length=100, blank=True)

    # Company data snapshot (editable per proposal)
    company_data = models.JSONField(default=dict)

    # Project
    project_name      = models.CharField(max_length=200, blank=True)
    project_goal      = models.TextField(blank=True)
    biz_description   = models.TextField(blank=True)
    selected_features = models.TextField(blank=True)

    # Content lists (stored so they can be customised after creation)
    scope        = models.JSONField(default=list)
    out_of_scope = models.JSONField(default=list)
    phases       = models.JSONField(default=list)
    conditions   = models.JSONField(default=list)

    # Timeline + payment
    timeline       = models.CharField(max_length=100, blank=True)
    start_date     = models.CharField(max_length=20, blank=True)
    payment_method = models.CharField(max_length=30, default='50-50')
    payment_custom = models.TextField(blank=True)

    # Pricing snapshot — copied from Lead, can be overridden
    package            = models.CharField(max_length=100, blank=True)
    package_base_price = models.IntegerField(default=0)
    extras             = models.JSONField(default=list)   # [{name, price}]
    extras_price       = models.IntegerField(default=0)
    rush               = models.BooleanField(default=False)
    rush_amount        = models.IntegerField(default=0)
    discount_pct       = models.IntegerField(default=15)
    discount_amount    = models.IntegerField(default=0)
    taxable_base       = models.IntegerField(default=0)
    iva_pct            = models.IntegerField(default=21)
    iva_amount         = models.IntegerField(default=0)
    total_with_iva     = models.IntegerField(default=0)
    maintenance_plan   = models.CharField(max_length=50, blank=True)
    maintenance_price  = models.IntegerField(default=0)

    notes = models.TextField(blank=True)

    # Client acceptance data
    accepted_by_name   = models.CharField(max_length=200, blank=True)
    accepted_nif       = models.CharField(max_length=30, blank=True)
    accepted_signature = models.TextField(blank=True)
    accepted_at        = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.number} — {self.lead.name} [{self.get_status_display()}]'

    @classmethod
    def generate_number(cls) -> str:
        today  = timezone.localdate()
        prefix = f'WI-{today.strftime("%Y%m%d")}-'
        last   = (cls.objects.filter(number__startswith=prefix)
                  .order_by('-number')
                  .values_list('number', flat=True)
                  .first())
        if last:
            try:
                seq = int(last.split('-')[-1]) + 1
            except (ValueError, IndexError):
                seq = 1
        else:
            seq = 1
        return f'{prefix}{seq:04d}'

    def compute_totals(self):
        """Recompute all totals from component prices."""
        _r = lambda x: math.floor(x + 0.5)  # JS-compatible round (half-up)
        subtotal = self.package_base_price + self.extras_price
        if self.rush:
            self.rush_amount = _r(subtotal * 0.25)
            subtotal += self.rush_amount
        else:
            self.rush_amount = 0
        self.discount_amount = _r(subtotal * self.discount_pct / 100)
        self.taxable_base    = subtotal - self.discount_amount
        self.iva_amount      = _r(self.taxable_base * self.iva_pct / 100)
        self.total_with_iva  = self.taxable_base + self.iva_amount

    @property
    def is_editable(self) -> bool:
        # Client viewing the link auto-flips status to "viewed" — that alone
        # shouldn't lock editing. Only a signed/accepted proposal is final.
        return self.status in (self.ST_DRAFT, self.ST_SENT, self.ST_VIEWED)

    @property
    def is_client_visible(self) -> bool:
        return self.status in (self.ST_SENT, self.ST_VIEWED, self.ST_ACCEPTED)

    @property
    def expires_date(self):
        return self.issued_at + timedelta(days=self.valid_days)


# ── UPLOAD PATH HELPERS ────────────────────────────────────────────────────────

def _invoice_upload_path(instance, filename):
    safe = ''.join(c for c in filename if c.isalnum() or c in '._- ').rstrip()
    return f'invoices/{instance.lead_id}/{safe}'


def _evidence_upload_path(instance, filename):
    safe = ''.join(c for c in filename if c.isalnum() or c in '._- ').rstrip()
    return f'evidence/{instance.lead_id}/{safe}'


# ── PROJECT MILESTONES ─────────────────────────────────────────────────────────

class ProjectMilestone(models.Model):
    ST_PENDING     = 'pending'
    ST_IN_PROGRESS = 'in_progress'
    ST_DONE        = 'done'
    ST_BLOCKED     = 'blocked'

    STATUS_CHOICES = [
        (ST_PENDING,     'Pendiente'),
        (ST_IN_PROGRESS, 'En progreso'),
        (ST_DONE,        'Completado'),
        (ST_BLOCKED,     'Bloqueado'),
    ]

    lead           = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name='milestones')
    title          = models.CharField(max_length=200)
    description    = models.TextField(blank=True)
    due_date       = models.DateField(null=True, blank=True)
    completed_date = models.DateField(null=True, blank=True)
    status         = models.CharField(max_length=20, choices=STATUS_CHOICES, default=ST_PENDING)
    notes          = models.TextField(blank=True)
    created_at     = models.DateTimeField(auto_now_add=True)
    updated_at     = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['due_date', 'created_at']

    def __str__(self):
        return f'{self.title} (Lead #{self.lead_id})'


# ── WORK LOG ───────────────────────────────────────────────────────────────────

class WorkLog(models.Model):
    CAT_DESIGN      = 'design'
    CAT_DEVELOPMENT = 'development'
    CAT_CONTENT     = 'content'
    CAT_MEETING     = 'meeting'
    CAT_REVISION    = 'revision'
    CAT_DELIVERY    = 'delivery'
    CAT_OTHER       = 'other'

    CATEGORY_CHOICES = [
        (CAT_DESIGN,      'Diseño'),
        (CAT_DEVELOPMENT, 'Desarrollo'),
        (CAT_CONTENT,     'Contenido'),
        (CAT_MEETING,     'Reunión'),
        (CAT_REVISION,    'Revisión'),
        (CAT_DELIVERY,    'Entrega'),
        (CAT_OTHER,       'Otro'),
    ]

    lead            = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name='work_logs')
    date            = models.DateField()
    hours           = models.DecimalField(max_digits=5, decimal_places=1)
    category        = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default=CAT_DEVELOPMENT)
    description     = models.TextField()
    deliverable_url = models.CharField(max_length=500, blank=True)
    notes           = models.TextField(blank=True)
    created_at      = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date', '-created_at']

    def __str__(self):
        return f'{self.date} {self.hours}h — {self.description[:60]} (Lead #{self.lead_id})'


# ── PAYMENT RECORDS ────────────────────────────────────────────────────────────

class PaymentRecord(models.Model):
    MT_BANK_TRANSFER = 'bank_transfer'
    MT_BIZUM         = 'bizum'
    MT_PAYPAL        = 'paypal'
    MT_CASH          = 'cash'
    MT_STRIPE        = 'stripe'
    MT_OTHER         = 'other'

    ST_PENDING  = 'pending'
    ST_RECEIVED = 'received'
    ST_PARTIAL  = 'partial'
    ST_REFUNDED = 'refunded'

    METHOD_CHOICES = [
        (MT_BANK_TRANSFER, 'Transferencia bancaria'),
        (MT_BIZUM,         'Bizum'),
        (MT_PAYPAL,        'PayPal'),
        (MT_CASH,          'Efectivo'),
        (MT_STRIPE,        'Stripe'),
        (MT_OTHER,         'Otro'),
    ]
    STATUS_CHOICES = [
        (ST_PENDING,  'Pendiente'),
        (ST_RECEIVED, 'Recibido'),
        (ST_PARTIAL,  'Parcial'),
        (ST_REFUNDED, 'Devuelto'),
    ]

    lead         = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name='payments')
    concept      = models.CharField(max_length=300)
    amount       = models.IntegerField()          # euros
    payment_date = models.DateField()
    method       = models.CharField(max_length=20, choices=METHOD_CHOICES, default=MT_BANK_TRANSFER)
    reference    = models.CharField(max_length=200, blank=True)   # bank ref or invoice number
    invoice_file = models.FileField(upload_to=_invoice_upload_path, null=True, blank=True)
    status       = models.CharField(max_length=20, choices=STATUS_CHOICES, default=ST_RECEIVED)
    notes        = models.TextField(blank=True)
    created_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-payment_date', '-created_at']

    def __str__(self):
        return f'{self.concept} {self.amount}€ ({self.payment_date}) Lead #{self.lead_id}'


# ── EVIDENCE FILES ─────────────────────────────────────────────────────────────

class EvidenceFile(models.Model):
    CAT_SCREENSHOT = 'screenshot'
    CAT_INVOICE    = 'invoice'
    CAT_APPROVAL   = 'approval'
    CAT_CONTRACT   = 'contract'
    CAT_DELIVERY   = 'delivery'
    CAT_OTHER      = 'other'

    CATEGORY_CHOICES = [
        (CAT_SCREENSHOT, 'Captura de pantalla'),
        (CAT_INVOICE,    'Factura'),
        (CAT_APPROVAL,   'Aprobación del cliente'),
        (CAT_CONTRACT,   'Contrato'),
        (CAT_DELIVERY,   'Entregable'),
        (CAT_OTHER,      'Otro'),
    ]

    lead       = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name='evidence')
    category   = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default=CAT_OTHER)
    title      = models.CharField(max_length=200)
    file       = models.FileField(upload_to=_evidence_upload_path, null=True, blank=True)
    url        = models.CharField(max_length=500, blank=True)
    notes      = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.title} ({self.category}) Lead #{self.lead_id}'
