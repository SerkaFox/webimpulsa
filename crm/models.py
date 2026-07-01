from django.db import models


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

    # ── client data ───────────────────────────────────────────────────────────
    name     = models.CharField(max_length=200)
    email    = models.CharField(max_length=200, blank=True)
    phone    = models.CharField(max_length=50, blank=True)
    biz_type = models.CharField(max_length=100, blank=True)

    # ── package / calculator data ─────────────────────────────────────────────
    package            = models.CharField(max_length=100, blank=True)
    package_base_price = models.IntegerField(default=0)
    extras             = models.JSONField(default=list)   # list of extra names
    extras_price       = models.IntegerField(default=0)
    rush               = models.BooleanField(default=False)
    maintenance_plan   = models.CharField(max_length=50, blank=True)
    maintenance_price  = models.IntegerField(default=0)
    estimated_price    = models.IntegerField(default=0)   # after discount
    discount_pct       = models.IntegerField(default=15)

    # ── CRM fields ────────────────────────────────────────────────────────────
    source  = models.CharField(max_length=30, choices=SOURCE_CHOICES, default=SRC_CALCULATOR)
    status  = models.CharField(max_length=30, choices=STATUS_CHOICES, default=ST_NUEVO)
    notes   = models.TextField(blank=True)

    # raw payload stored for audit / future re-processing
    raw_data = models.JSONField(default=dict)

    # ── timestamps ────────────────────────────────────────────────────────────
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Lead #{self.pk} — {self.name} ({self.package or "—"})'

    @property
    def contact(self):
        return self.email or self.phone
