"""
Proposal content constants for WebImpulsa.

== EDIT COMPANY DATA ==
Set environment variables WI_COMPANY_* or edit WI_COMPANY below with real
legal/fiscal data before sending proposals to clients.
"""
import os

# ── Company data ── edit here or via environment variables ────────────────────
# TODO: fill legal_name, nif, address when company registration is confirmed
WI_COMPANY = {
    'trade_name': os.getenv('WI_COMPANY_NAME',    'WebImpulsa'),
    'legal_name': os.getenv('WI_COMPANY_LEGAL',   ''),
    'nif':        os.getenv('WI_COMPANY_NIF',     ''),
    'email':      os.getenv('WI_COMPANY_EMAIL',   'info@webimpulsa.es'),
    'phone':      os.getenv('WI_COMPANY_PHONE',   '+34 613 708 322'),
    'website':    os.getenv('WI_COMPANY_WEBSITE', 'https://webimpulsa.es'),
    'address':    os.getenv('WI_COMPANY_ADDRESS', ''),
    'city':       os.getenv('WI_COMPANY_CITY',    ''),
    'logo_url':   '/static/wi/img/logo.webp',
}

# ── Extras price table ── mirrors EXTRAS_CONFIG in tatiana.html ───────────────
EXTRAS_PRICES = {
    'Diseño premium':              150,
    'Textos que venden':           120,
    'Aparecer en Google':          200,
    'Ficha en Google Maps':         80,
    'Formulario inteligente':       90,
    'Botón de WhatsApp':            40,
    'Citas y reservas online':     180,
    'Cobros y conexiones online':  120,
    'Web en varios idiomas':       250,
    'Estadísticas de ventas':      120,
    'Subir catálogo completo':     150,
    'Avisos antes de cada cita':    80,
    'Asistente automático 24h':    240,
    'Correo con tu dominio':        90,
    'Galería de Instagram':         80,
    'Zona privada para clientes':  350,
    'Documentos automáticos PDF':  180,
    'Datos en Excel / Sheets':     120,
    'Panel para tu equipo':        350,
    'App para móvil':              590,
}

# ── Project scope ── mirrors PROJECT_SCOPES in proposal-template.js ───────────
PROJECT_SCOPES = {
    'Landing page': [
        'Página principal optimizada para conversión',
        'Diseño responsive adaptado a móvil, tablet y ordenador',
        'Secciones de servicios, beneficios, contacto y llamada a la acción',
        'Formulario de contacto básico',
        'Integración con WhatsApp',
        'Optimización básica SEO on-page',
        'Publicación inicial',
    ],
    'Web profesional': [
        'Hasta 5 secciones o páginas principales',
        'Diseño responsive adaptado a la imagen del negocio',
        'Formulario de contacto',
        'Integración WhatsApp',
        'Optimización SEO básica',
        'Configuración básica de analítica si aplica',
        'Publicación inicial',
    ],
    'Web con reservas': [
        'Todo lo incluido en una web profesional',
        'Sistema de reservas o citas online',
        'Gestión básica de servicios y disponibilidad',
        'Notificaciones básicas por email o WhatsApp según alcance',
        'Panel o integración de gestión según el caso',
        'Pruebas funcionales antes de publicación',
    ],
    'Tienda online': [
        'Catálogo inicial de productos o servicios',
        'Carrito o flujo de pedido',
        'Configuración básica de pagos si aplica',
        'Estructura de páginas legales básicas, sin redacción legal definitiva',
        'Formación básica de uso',
        'Publicación inicial',
    ],
    'Proyecto a medida': [
        'Análisis funcional del flujo de trabajo',
        'Diseño de estructura y pantallas principales',
        'Desarrollo de funcionalidades acordadas',
        'Integraciones descritas expresamente en el alcance',
        'Pruebas funcionales y ajustes razonables',
        'Publicación o entrega inicial',
    ],
    'Proyecto existente': [
        'Revisión del proyecto actual',
        'Mejoras o ampliaciones descritas en el alcance',
        'Corrección de incidencias técnicas acordadas',
        'Integraciones o automatizaciones seleccionadas',
        'Pruebas sobre las partes intervenidas',
        'Entrega de resumen de cambios',
    ],
    'Solo mantenimiento': [
        'Revisión técnica inicial',
        'Actualizaciones y mantenimiento según plan seleccionado',
        'Correcciones menores dentro del tiempo contratado',
        'Backups y seguimiento según plan',
        'Soporte mensual facturado aparte',
    ],
}

DEFAULT_SCOPE = PROJECT_SCOPES['Proyecto a medida'][:]

DEADLINES = {
    'Landing page':       '5-10 días laborables',
    'Web profesional':    '10-20 días laborables',
    'Web con reservas':   '15-30 días laborables',
    'Tienda online':      '20-40 días laborables',
    'Proyecto a medida':  'Según alcance',
    'Proyecto existente': 'Según alcance',
    'Solo mantenimiento': 'Activación en 2-5 días laborables',
}

OUT_OF_SCOPE = [
    'Redacción legal definitiva de textos legales',
    'Compra de dominio',
    'Hosting',
    'Licencias externas',
    'Pasarelas de pago',
    'Fotografías profesionales',
    'Traducciones',
    'Campañas publicitarias',
    'Funcionalidades no descritas expresamente',
]

PHASES = [
    'Fase 1: Briefing y recopilación de material',
    'Fase 2: Diseño y estructura',
    'Fase 3: Desarrollo',
    'Fase 4: Revisión y ajustes',
    'Fase 5: Publicación',
    'Fase 6: Soporte inicial',
]

CONDITIONS = [
    'Este documento constituye una propuesta comercial/presupuesto y no una factura.',
    'La aceptación del presupuesto por escrito, email, WhatsApp o firma implica conformidad con el alcance, precio y condiciones indicadas.',
    'El cliente se compromete a facilitar textos, imágenes, logotipos, accesos y materiales necesarios.',
    'Los retrasos en la entrega de materiales por parte del cliente pueden modificar los plazos.',
    'Se incluyen ajustes razonables durante la fase de revisión. Cambios sustanciales o nuevas funcionalidades fuera del alcance se presupuestarán aparte.',
    'Dominio, hosting, licencias, pasarelas de pago, plugins premium, fotografías, traducciones y servicios de terceros no están incluidos salvo indicación expresa.',
    'WebImpulsa no se responsabiliza de interrupciones o cambios de condiciones de servicios externos.',
    'La entrega final se realizará una vez abonado el importe pendiente.',
    'El cliente es responsable de la veracidad del contenido facilitado y de contar con derechos de uso sobre imágenes, marcas y materiales enviados.',
    'Los textos legales definitivos, política de privacidad, cookies, aviso legal y condiciones de contratación deben ser revisados por un profesional legal si el proyecto lo requiere.',
    'La propuesta tiene una validez de 15 días naturales salvo indicación distinta.',
    'Los importes pueden estar sujetos a IVA u otros impuestos aplicables.',
]
