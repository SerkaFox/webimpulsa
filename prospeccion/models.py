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
    SOURCE_GOOGLE_PLACES = 'google_places'
    SOURCE_CHOICES = [
        (SOURCE_MANUAL, 'Manual'),
        (SOURCE_MAP_CLICK, 'Clic en el mapa'),
        (SOURCE_CSV, 'Importación CSV'),
        (SOURCE_PUBLIC_QUIZ, 'Chequeo público'),
        (SOURCE_GOOGLE_PLACES, 'Búsqueda de Google Places'),
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
    # Solo el identificador — nunca reseñas, fotos, rating ni horario. Sirve
    # para deduplicar con certeza y para volver a "Abrir en Google Maps" sin
    # tener que guardar más contenido de Google del que el equipo vio y
    # confirmó al crear el prospecto.
    google_place_id = models.CharField(max_length=200, blank=True, db_index=True)

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
    # — lo da la propia empresa (checkbox al final de su chequeo personal);
    # ya no hay una segunda confirmación administrativa aparte.
    publish_consent = models.BooleanField(default=False)
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
            models.Index(fields=['publish_consent']),
        ]

    def __str__(self):
        return f'{self.name} ({self.sector})'

    def is_published(self):
        return bool(self.publish_consent and not self.publish_revoked_at)


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

    # enlace público de solo lectura a este resultado (para compartir el
    # informe sin exponer nada del panel interno) y datos de envío por
    # WhatsApp al propio respondente — nunca al revés (nunca guardamos aquí
    # el número de Tania, solo el de quien pidió recibir su informe).
    report_token = models.CharField(max_length=64, unique=True, db_index=True, default=_new_token)
    respondent_phone = models.CharField(max_length=50, blank=True)
    respondent_consent_at = models.DateTimeField(null=True, blank=True)
    report_sent_at = models.DateTimeField(null=True, blank=True)

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


class ProspectPhoto(models.Model):
    """Fotos reales tomadas in situ por el equipo (varios ángulos del
    negocio) — complementa la única foto que suele haber en la ficha de
    Google. Solo referencia visual interna, no se publica automáticamente
    en ningún sitio."""

    # related_name deliberadamente distinto de "photos" — ese nombre está
    # reservado por el test de seguridad que garantiza que BusinessProspect
    # nunca tenga un campo "photos" con datos de Google Places (ver
    # AddFromPlaceTests). Estas son fotos propias, tomadas por el equipo, sin
    # relación con las fotos de Google que deliberadamente nunca se piden.
    prospect = models.ForeignKey(BusinessProspect, on_delete=models.CASCADE, related_name='site_photos')
    image = models.ImageField(upload_to='prospeccion_fotos/%Y/%m/')
    caption = models.CharField(max_length=200, blank=True)
    uploaded_by = models.CharField(max_length=120, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Foto de {self.prospect_id} ({self.created_at:%d/%m/%Y})'


class PlacesApiUsage(models.Model):
    """Contador diario ORIGINAL de llamadas a la Google Places API — se
    mantiene solo por compatibilidad con datos históricos (antes de que
    existiera el desglose por tipo de request en PlacesApiRequestLog /
    PlacesApiMonthlyCounter, más abajo). No se le añaden más filas nuevas
    desde que existe el control por request_type."""

    date = models.DateField(unique=True)
    count = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f'{self.date}: {self.count} búsquedas'


# ── Control real de gasto en Google Places (por tipo de request/SKU) ─────────
#
# El campo mask (FIELD_MASK en places.py) determina el SKU real que Google
# factura — no el endpoint por sí solo. Actualmente el mask incluye teléfono
# y website (Contact Data), así que tanto Text Search como Nearby Search
# caen en el tier "Enterprise". Si el mask cambiara a futuro para excluir
# esos campos, _field_tier() en places.py reclasificaría automáticamente
# hacia "pro" — por eso el enum ya contempla ambos tiers desde ahora, y
# también Place Details (no usado hoy en este CRM, pero sí en el proyecto
# hermano `anna`, con su propia clave — se deja preparado por si algún día
# se centraliza aquí).
PLACES_REQUEST_TYPE_CHOICES = [
    ('text_search_enterprise', 'Text Search — Enterprise'),
    ('nearby_search_enterprise', 'Nearby Search — Enterprise'),
    ('place_details_enterprise', 'Place Details — Enterprise'),
    ('place_details_enterprise_atmosphere', 'Place Details — Enterprise + Atmosphere'),
    ('text_search_pro', 'Text Search — Pro'),
    ('nearby_search_pro', 'Nearby Search — Pro'),
    # Solo para los datos migrados desde PlacesApiUsage (antes de este
    # control), donde no hay forma real de saber si cada llamada fue texto
    # o nearby — nunca se inventa el desglose.
    ('legacy_unknown', 'Histórico sin desglosar (anterior a este control)'),
]


class PlacesApiMonthlyCounter(models.Model):
    """Contador atómico por (mes de facturación de Google, tipo de request).
    El mes de facturación se calcula en America/Los_Angeles (huso horario
    que usa Google para el ciclo de facturación de Cloud), NUNCA en la zona
    horaria del servidor — ver billing_month_now() en places.py.

    reserved_count se incrementa ANTES de llamar a Google (con select_for_
    update dentro de una transacción — ver places.py:_reserve_call), así
    que success_count + error_count <= reserved_count siempre (nunca al
    revés): "reservado" significa "se decidió intentar la llamada real",
    no "se completó con éxito"."""

    billing_month = models.CharField(max_length=7, db_index=True)  # 'YYYY-MM' en America/Los_Angeles
    request_type = models.CharField(max_length=40, choices=PLACES_REQUEST_TYPE_CHOICES, db_index=True)
    reserved_count = models.PositiveIntegerField(default=0)
    success_count = models.PositiveIntegerField(default=0)
    error_count = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['billing_month', 'request_type'], name='uniq_places_counter_month_type'),
        ]

    def __str__(self):
        return f'{self.billing_month} · {self.request_type}: {self.reserved_count}'


class PlacesApiRequestLog(models.Model):
    """Registro individual de cada intento real de llamada a Google Places
    (incluye los bloqueados por límite, para poder ver cuántas veces el
    equipo se topó con el tope). Deliberadamente NO guarda: la clave de API,
    la URL completa con la clave, el texto/coordenadas en crudo (solo un
    hash, para poder detectar búsquedas repetidas sin poder reconstruir qué
    se buscó exactamente), ni la respuesta completa de Google."""

    # default=timezone.now (no auto_now_add) a propósito: para uso normal se
    # comporta igual (se rellena solo al crear), pero permite que la
    # migración de datos legacy (0009) fije la fecha histórica real en vez
    # de "ahora" — auto_now_add ignora cualquier valor pasado explícitamente,
    # incluso en bulk_create.
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    billing_month = models.CharField(max_length=7, db_index=True)
    request_type = models.CharField(max_length=40, choices=PLACES_REQUEST_TYPE_CHOICES, db_index=True)
    endpoint = models.CharField(max_length=200, blank=True)
    # Nullable a propósito: el CRM usa una única contraseña compartida (ver
    # _crm_auth en crm/views.py), no login individual — no hay forma real de
    # saber QUÉ persona del equipo hizo cada búsqueda todavía.
    user = models.ForeignKey(StaffMember, null=True, blank=True, on_delete=models.SET_NULL)
    success = models.BooleanField(default=False)
    response_status = models.IntegerField(null=True, blank=True)
    error_type = models.CharField(max_length=120, blank=True)
    result_count = models.IntegerField(null=True, blank=True)
    duration_ms = models.IntegerField(null=True, blank=True)
    query_hash = models.CharField(max_length=64, blank=True)
    coordinates_hash = models.CharField(max_length=64, blank=True)
    radius_m = models.IntegerField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['billing_month', 'request_type']),
        ]

    def __str__(self):
        return f'{self.created_at:%Y-%m-%d %H:%M} · {self.request_type} · {"OK" if self.success else "ERROR"}'


class PlacesApiLimitNotification(models.Model):
    """Marca de "ya se avisó este umbral este mes" — para que el 70/85/95/100%
    se notifique una única vez por (mes, tipo), no en cada carga de página."""

    billing_month = models.CharField(max_length=7, db_index=True)
    request_type = models.CharField(max_length=40, choices=PLACES_REQUEST_TYPE_CHOICES)
    threshold = models.PositiveSmallIntegerField()  # 70, 85, 95, 100
    notified_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['billing_month', 'request_type', 'threshold'], name='uniq_places_notif_month_type_threshold'
            ),
        ]

    def __str__(self):
        return f'{self.billing_month} · {self.request_type} · {self.threshold}%'
