import hashlib
import os
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
