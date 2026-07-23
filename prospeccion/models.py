import secrets

from django.db import models
from django.utils import timezone


def _new_token():
    return secrets.token_urlsafe(32)


# Versión del texto/base legal de los consentimientos de BusinessContact —
# cambiar este valor (y guardar el texto anterior en otro sitio) el día que
# cambie la redacción, para poder saber siempre qué versión aceptó cada
# contacto en su momento.
CONSENT_TEXT_VERSION = 'v1-2026-07'


# Mismos sectores que el chequeo digital público (chequeo_digital.html CATEGORIES),
# para que un BusinessProspect pueda pre-rellenar/enlazar directamente su sector.
SECTOR_CHOICES = [
    ('salon', 'Salón de belleza / peluquería / estética'),
    ('bar', 'Bar / cafetería / restaurante'),
    ('taller', 'Taller / automoción / servicio técnico'),
    ('academia', 'Academia / cursos / formación'),
    ('clinica', 'Clínica / fisioterapia / salud privada'),
    ('tienda', 'Tienda local'),
    ('inmobiliaria', 'Inmobiliaria / reformas / servicios profesionales'),
    ('otro', 'Otro negocio local'),
]


class StaffMember(models.Model):
    name = models.CharField(max_length=120)
    active = models.BooleanField(default=True)
    color = models.CharField(max_length=7, blank=True)
    # Único campo de "rol" que existe en todo el proyecto: no hay cuentas ni
    # login individual (_crm_auth es un único password compartido), así que
    # esto no es un sistema de permisos completo — solo gatilla la única
    # acción que de verdad necesita distinguirse: confirmar publicación en el
    # mapa público. Quien confirma se elige explícitamente en el momento de
    # la acción (no hay sesión ligada a una persona), y se valida en servidor.
    can_confirm_publication = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class BusinessProspect(models.Model):
    SALES_DISCOVERED = 'discovered'
    SALES_PRE_AUDITED = 'pre_audited'
    SALES_CONTACTED = 'contacted'
    SALES_AUDITED = 'audited'
    SALES_PRESUPUESTO = 'presupuesto_created'
    SALES_WON = 'won'
    SALES_LOST = 'lost'
    SALES_DO_NOT_CONTACT = 'do_not_contact'
    SALES_ARCHIVED = 'archived'
    SALES_STATUS_CHOICES = [
        (SALES_DISCOVERED, 'Descubierto'),
        (SALES_PRE_AUDITED, 'Pre-auditado'),
        (SALES_CONTACTED, 'Contactado'),
        (SALES_AUDITED, 'Auditado'),
        (SALES_PRESUPUESTO, 'Presupuesto creado'),
        (SALES_WON, 'Ganado'),
        (SALES_LOST, 'Perdido'),
        (SALES_DO_NOT_CONTACT, 'No contactar'),
        (SALES_ARCHIVED, 'Archivado'),
    ]
    PRIORITY_CHOICES = [('low', 'Baja'), ('normal', 'Normal'), ('high', 'Alta')]

    SOURCE_MANUAL = 'manual'
    SOURCE_MAP_CLICK = 'map_click'
    SOURCE_CSV = 'csv_import'
    SOURCE_PUBLIC_QUIZ = 'public_quiz_upgrade'
    SOURCE_CHOICES = [
        (SOURCE_MANUAL, 'Manual'),
        (SOURCE_MAP_CLICK, 'Clic en el mapa'),
        (SOURCE_CSV, 'Importación CSV'),
        (SOURCE_PUBLIC_QUIZ, 'Chequeo público'),
    ]

    # identidad / color del marcador (sales_status, no el score)
    name = models.CharField(max_length=200)
    sector = models.CharField(max_length=30, choices=SECTOR_CHOICES, default='otro')
    sales_status = models.CharField(
        max_length=30, choices=SALES_STATUS_CHOICES, default=SALES_DISCOVERED, db_index=True
    )
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='normal')

    # ubicación — lat/lng planos (sqlite, sin PostGIS)
    address = models.CharField(max_length=300, blank=True)
    district = models.CharField(max_length=120, blank=True)
    municipality = models.CharField(max_length=120, blank=True)
    lat = models.FloatField(null=True, blank=True)
    lng = models.FloatField(null=True, blank=True)
    needs_manual_placement = models.BooleanField(default=False)

    # canales de contacto de la empresa (no de una persona concreta — ver BusinessContact)
    phone = models.CharField(max_length=50, blank=True)
    email = models.CharField(max_length=200, blank=True)
    website = models.CharField(max_length=300, blank=True)
    whatsapp = models.CharField(max_length=50, blank=True)
    social_links = models.JSONField(default=dict, blank=True)
    gmaps_url = models.CharField(max_length=500, blank=True)

    # denormalizado desde el último ChequeoAudit CONFIRMADO — para filtros rápidos del mapa
    has_website = models.BooleanField(null=True, blank=True)
    has_online_booking = models.BooleanField(null=True, blank=True)
    has_whatsapp_cta = models.BooleanField(null=True, blank=True)
    current_score = models.IntegerField(null=True, blank=True)

    source = models.CharField(max_length=30, choices=SOURCE_CHOICES, default=SOURCE_MANUAL)
    assigned_to = models.ForeignKey(
        StaffMember, null=True, blank=True, on_delete=models.SET_NULL, related_name='prospects'
    )
    staff_notes = models.TextField(blank=True)

    # enlace seguro para el modo personal /chequeo-digital/e/<token>/
    public_token = models.CharField(max_length=64, unique=True, db_index=True, default=_new_token)

    last_check_at = models.DateTimeField(null=True, blank=True)
    next_action_at = models.DateTimeField(null=True, blank=True)

    # enlace con el CRM existente — solo esta dirección (prospeccion -> crm), nunca al revés
    converted_client = models.ForeignKey(
        'crm.Lead', null=True, blank=True, on_delete=models.SET_NULL, related_name='prospeccion_source'
    )

    # consentimiento para el mapa PÚBLICO (aparte de los consentimientos de BusinessContact)
    publish_consent = models.BooleanField(default=False)
    publish_confirmed_by_staff = models.BooleanField(default=False)
    publish_consent_at = models.DateTimeField(null=True, blank=True)
    publish_revoked_at = models.DateTimeField(null=True, blank=True)

    dedupe_key = models.CharField(max_length=64, db_index=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['lat', 'lng']),
            models.Index(fields=['sector', 'sales_status']),
            models.Index(fields=['assigned_to', 'next_action_at']),
            models.Index(fields=['publish_consent', 'publish_confirmed_by_staff']),
        ]

    def __str__(self):
        return f'{self.name} ({self.sector})'

    def is_published(self):
        return bool(
            self.publish_consent and self.publish_confirmed_by_staff and not self.publish_revoked_at
        )


class BusinessContact(models.Model):
    ROLE_OWNER = 'owner'
    ROLE_MANAGER = 'manager'
    ROLE_ADMIN = 'administrator'
    ROLE_EMPLOYEE = 'employee'
    ROLE_MARKETING = 'marketing'
    ROLE_UNKNOWN = 'unknown'
    ROLE_CHOICES = [
        (ROLE_OWNER, 'Dueño/a'),
        (ROLE_MANAGER, 'Gerente'),
        (ROLE_ADMIN, 'Administración'),
        (ROLE_EMPLOYEE, 'Empleado/a'),
        (ROLE_MARKETING, 'Marketing'),
        (ROLE_UNKNOWN, 'Desconocido'),
    ]
    CHANNEL_CHOICES = [('whatsapp', 'WhatsApp'), ('email', 'Email'), ('phone', 'Teléfono')]

    prospect = models.ForeignKey(BusinessProspect, on_delete=models.CASCADE, related_name='contacts')
    name = models.CharField(max_length=200, blank=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_OWNER)
    phone = models.CharField(max_length=50, blank=True)
    whatsapp = models.CharField(max_length=50, blank=True)
    email = models.CharField(max_length=200, blank=True)
    preferred_channel = models.CharField(max_length=20, choices=CHANNEL_CHOICES, default='whatsapp')
    is_primary = models.BooleanField(default=False)
    notes = models.TextField(blank=True)

    # consentimientos separados y revocables — nunca se infieren uno del otro.
    # Cada finalidad tiene su propia fecha de revocación (no una compartida),
    # para poder revocar el contacto comercial sin tocar el envío del informe
    # ya solicitado, o viceversa. Además de cuándo y cómo, se guarda QUÉ
    # versión del texto/base legal se mostró (consent_config.CONSENT_TEXT_VERSION)
    # y QUIÉN lo registró (nombre de StaffMember, o 'autoservicio' si lo hizo
    # la propia empresa) — necesario para poder demostrar más adelante
    # exactamente qué se aceptó y quién lo dejó constancia.
    consent_receive_report = models.BooleanField(default=False)
    consent_receive_report_at = models.DateTimeField(null=True, blank=True)
    consent_receive_report_method = models.CharField(max_length=50, blank=True)
    consent_receive_report_version = models.CharField(max_length=20, blank=True)
    consent_receive_report_actor = models.CharField(max_length=120, blank=True)
    consent_receive_report_revoked_at = models.DateTimeField(null=True, blank=True)
    consent_commercial_contact = models.BooleanField(default=False)
    consent_commercial_contact_at = models.DateTimeField(null=True, blank=True)
    consent_commercial_contact_method = models.CharField(max_length=50, blank=True)
    consent_commercial_contact_version = models.CharField(max_length=20, blank=True)
    consent_commercial_contact_actor = models.CharField(max_length=120, blank=True)
    consent_commercial_contact_revoked_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.name or f'Contacto de {self.prospect_id}'


class Interaction(models.Model):
    TYPE_VISIT = 'visit'
    TYPE_CALL = 'call'
    TYPE_WHATSAPP = 'whatsapp'
    TYPE_EMAIL = 'email'
    TYPE_QUIZ_STARTED = 'quiz_started'
    TYPE_QUIZ_COMPLETED = 'quiz_completed'
    TYPE_REPORT_SENT = 'report_sent'
    TYPE_MEETING = 'meeting'
    TYPE_PRESUPUESTO_CREATED = 'presupuesto_created'
    TYPE_WON = 'won'
    TYPE_LOST = 'lost'
    TYPE_CHOICES = [
        (TYPE_VISIT, 'Visita'),
        (TYPE_CALL, 'Llamada'),
        (TYPE_WHATSAPP, 'WhatsApp'),
        (TYPE_EMAIL, 'Email'),
        (TYPE_QUIZ_STARTED, 'Chequeo iniciado'),
        (TYPE_QUIZ_COMPLETED, 'Chequeo completado'),
        (TYPE_REPORT_SENT, 'Informe enviado'),
        (TYPE_MEETING, 'Reunión'),
        (TYPE_PRESUPUESTO_CREATED, 'Presupuesto creado'),
        (TYPE_WON, 'Ganado'),
        (TYPE_LOST, 'Perdido'),
    ]

    prospect = models.ForeignKey(BusinessProspect, on_delete=models.CASCADE, related_name='interactions')
    staff_member = models.ForeignKey(StaffMember, null=True, blank=True, on_delete=models.SET_NULL)
    type = models.CharField(max_length=30, choices=TYPE_CHOICES)
    date = models.DateTimeField(default=timezone.now)
    result = models.TextField(blank=True)
    next_action = models.CharField(max_length=300, blank=True)
    next_action_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date']
        indexes = [models.Index(fields=['prospect', 'date'])]

    def __str__(self):
        return f'{self.get_type_display()} — {self.prospect_id}'


class ChequeoAudit(models.Model):
    """Snapshot inmutable de un envío del chequeo. Nunca se actualiza in-place:
    una nueva revisión crea una fila nueva, para conservar el historial completo."""

    MODE_PUBLIC = 'public'
    MODE_PERSONAL = 'personal'
    MODE_CHOICES = [(MODE_PUBLIC, 'Público'), (MODE_PERSONAL, 'Personal')]

    STAGE_PRELIMINAR = 'preliminar'
    STAGE_CONFIRMADO = 'confirmado'
    STAGE_CHOICES = [(STAGE_PRELIMINAR, 'Preliminar'), (STAGE_CONFIRMADO, 'Confirmado')]

    prospect = models.ForeignKey(
        BusinessProspect, null=True, blank=True, on_delete=models.CASCADE, related_name='audits'
    )
    mode = models.CharField(max_length=10, choices=MODE_CHOICES, default=MODE_PUBLIC)
    stage = models.CharField(max_length=15, choices=STAGE_CHOICES, default=STAGE_PRELIMINAR)

    # identidad ligera para el chequeo público anónimo (resume / rate-limit), sin PII
    session_key = models.CharField(max_length=64, blank=True, db_index=True)

    sector = models.CharField(max_length=30, choices=SECTOR_CHOICES)
    questionnaire_version = models.CharField(max_length=20)

    # [{question_id, value, source: 'public_check'|'respondent'|'webimpulsa', comment, evidence_url}]
    answers = models.JSONField(default=list)

    score = models.IntegerField(default=0)
    category_scores = models.JSONField(default=dict)
    good_ids = models.JSONField(default=list)
    fix_ids = models.JSONField(default=list)
    sector_benchmark = models.IntegerField(default=75)

    ip_hash = models.CharField(max_length=64, blank=True)
    user_agent = models.CharField(max_length=500, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['prospect', '-created_at']),
            models.Index(fields=['session_key']),
        ]

    def __str__(self):
        who = self.prospect.name if self.prospect_id else 'público'
        return f'Audit {who} — {self.score}/100 ({self.stage})'
