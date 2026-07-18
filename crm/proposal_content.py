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
    'trade_name': os.getenv('WI_COMPANY_NAME',    'Web-Impulsa'),
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

# ── Extras descriptions ── mirrors the `ex` object (ES) in tatiana.html — used
# to describe, in the proposal's "Alcance"/"No incluido" sections, exactly what
# each purchased/non-purchased extra means, so the scope always matches what the
# client actually paid for. ─────────────────────────────────────────────────────
EXTRAS_DESCRIPTIONS = {
    'Diseño premium': 'Animaciones suaves, tipografías de pago, elementos visuales únicos y una maquetación más cuidada.',
    'Textos que venden': 'Redacción de todos los textos de la web: descripciones de servicios, titulares, frases de confianza y llamadas a la acción.',
    'Aparecer en Google': 'Optimización SEO avanzada y seguimiento continuo para mejorar el posicionamiento en buscadores (más allá de las etiquetas básicas incluidas de serie).',
    'Ficha en Google Maps': 'Creación y optimización del perfil de Google Maps/Google Business (foto, horario, valoraciones, dirección).',
    'Formulario inteligente': 'Formulario de contacto multi-paso, con campos condicionales y envío directo a email o WhatsApp.',
    'Botón de WhatsApp': 'Botón flotante de WhatsApp visible en todas las páginas de la web (más visible que el enlace de contacto básico incluido de serie).',
    'Citas y reservas online': 'Calendario integrado para que los clientes reserven cita o servicio ellos solos, con aviso al negocio en cada nueva reserva.',
    'Cobros y conexiones online': 'Conexión de la web con una pasarela de pago y sincronización automática con sistema de pedidos, agenda de clientes u otras herramientas ya en uso.',
    'Web en varios idiomas': 'Toda la web disponible en dos o más idiomas, con selector de idioma para el visitante.',
    'Estadísticas de ventas': 'Panel de métricas: productos más vendidos, carritos abandonados, origen de los clientes.',
    'Subir catálogo completo': 'Carga masiva de todos los productos desde un archivo Excel.',
    'Avisos antes de cada cita': 'Recordatorio automático por WhatsApp o email al cliente 24 horas antes de cada cita (reduce las ausencias).',
    'Asistente automático 24h': 'Bot conectado a WhatsApp o Telegram que responde preguntas frecuentes y recoge solicitudes sin intervención humana.',
    'Correo con tu dominio': 'Configuración de correo profesional con dominio propio (nombre@tuempresa.com), incluyendo DNS, SSL y redirecciones.',
    'Galería de Instagram': 'Conexión de la cuenta de Instagram para mostrar automáticamente las últimas fotos o trabajos en la web.',
    'Zona privada para clientes': 'Área protegida con contraseña donde los clientes ven sus pedidos, reservas, facturas o documentos.',
    'Documentos automáticos PDF': 'Generación automática de presupuestos, partes de trabajo o confirmaciones en PDF al recibir un pedido o cita.',
    'Datos en Excel / Sheets': 'Sincronización automática de reservas, pedidos o solicitudes con Google Sheets o Excel Online.',
    'Panel para tu equipo': 'Panel interno con acceso diferenciado por empleado para asignar tareas y controlar horarios.',
    'App para móvil': 'Aplicación instalable en el móvil para que clientes o empleados accedan al sistema sin depender del navegador.',
}

# ── Hours package / hosting ── mirrors HOURS_CONFIG / calcHostingToggle in tatiana.html ──
HOURS_PACKAGES = {
    'Bolsa 5 horas':  175,
    'Bolsa 10 horas': 320,
    'Bolsa 20 horas': 560,
    'Bolsa 40 horas': 1000,
}

HOSTING_PLAN_NAME  = 'Dominio + Hosting'
HOSTING_PLAN_PRICE = 15

# ── Project scope ── mirrors PROJECT_SCOPES in proposal-template.js ───────────
PROJECT_SCOPES = {
    'Landing page': [
        'Página principal optimizada para conversión',
        'Diseño responsive adaptado a móvil, tablet y ordenador',
        'Secciones de servicios, beneficios, contacto y llamada a la acción',
        'Formulario de contacto básico (nombre + mensaje)',
        'Enlace de contacto directo por WhatsApp en la sección de contacto (no incluye el botón flotante visible en todas las páginas, que es un extra opcional)',
        'Etiquetas de título y meta-descripción básicas para buscadores (el posicionamiento SEO avanzado y su seguimiento son un extra opcional)',
        'Publicación inicial',
    ],
    'Web profesional': [
        'Hasta 5 secciones o páginas principales',
        'Diseño responsive adaptado a la imagen del negocio',
        'Formulario de contacto',
        'Enlace de contacto directo por WhatsApp en la sección de contacto (no incluye el botón flotante visible en todas las páginas, que es un extra opcional)',
        'Etiquetas de título y meta-descripción básicas para buscadores (el posicionamiento SEO avanzado y su seguimiento son un extra opcional)',
        'Configuración básica de analítica si aplica',
        'Publicación inicial',
    ],
    'Web con reservas': [
        'Todo lo incluido en una web profesional',
        'Sistema de reservas o citas online',
        'Gestión básica de servicios y disponibilidad',
        'Aviso al negocio cada vez que se recibe una reserva nueva (los recordatorios automáticos al cliente antes de la cita son un extra opcional)',
        'Panel o integración de gestión según el caso',
        'Pruebas funcionales antes de publicación',
    ],
    'Tienda online': [
        'Catálogo inicial de productos o servicios',
        'Carrito o flujo de pedido',
        'Configuración de una pasarela de pago (según disponibilidad y condiciones del propio proveedor de pago)',
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

# ── Condiciones generales ── dos variantes según el tipo de cliente ───────────
# NOTA LEGAL: redacción propia razonable basada en TRLGDCU / Código de Comercio /
# LOPDGDD-RGPD. No sustituye la revisión de un abogado antes de usarse con clientes reales.
#
# BUSINESS = autónomo o empresa (bajo el art. 3 TRLGDCU, quien contrata para su
# actividad profesional no tiene la condición de "consumidor").
# CONSUMER = particular.

_COMMON_CONDITIONS = [
    'Este documento constituye un presupuesto/propuesta comercial y no una factura. La factura se emitirá conforme a la normativa fiscal aplicable tras la aceptación y/o el pago correspondiente.',
    'El inicio de los trabajos y los plazos indicados dependen de: (a) el pago según el calendario acordado, y (b) la entrega por el cliente de los materiales y accesos necesarios (textos, imágenes, logotipos, credenciales, etc.). Un retraso del cliente en la entrega de materiales desplaza proporcionalmente los plazos.',
    'El cliente es responsable de los textos, imágenes y contenidos que aporte, y de disponer de los derechos y la legalidad necesarios sobre ellos; de sus propias copias de seguridad de datos que no estén alojados por Web-Impulsa; de los accesos y credenciales que facilite; y de los servicios de terceros que decida utilizar (hosting externo, dominios, plugins, Google, WhatsApp Business, pasarelas de pago, etc.).',
    'Web-Impulsa no garantiza el funcionamiento ininterrumpido de servicios de terceros ajenos a su control (Google, WhatsApp, proveedores de hosting/dominio, plugins), ni resultados de posicionamiento SEO, posiciones concretas en buscadores, volumen de visitas, ventas, ni la ausencia de pérdida de clientes, por depender de factores externos no controlables por Web-Impulsa.',
    'El cliente debe revisar el sitio en la URL de pruebas (staging) y dar su conformidad por escrito antes de la publicación definitiva. Una vez aceptada la entrega, cualquier cambio adicional se gestiona y presupuesta aparte, salvo pacto expreso en contrario.',
    'Se incluyen ajustes razonables durante la fase de revisión previa a la entrega. Cambios sustanciales, nuevas funcionalidades o modificaciones fuera del alcance descrito se presupuestarán aparte.',
    'Dominio, hosting, licencias, pasarelas de pago, plugins premium, fotografías profesionales, traducciones y demás servicios de terceros no están incluidos salvo que se indiquen expresamente en el alcance de esta propuesta.',
    'Servicios de pago mensual (mantenimiento, bolsa de horas y/o hosting, cuando se contraten): se facturan por mensualidades adelantadas y se renuevan automáticamente cada mes salvo cancelación. El cliente puede cancelarlos con un preaviso de 15 días naturales, sin permanencia mínima salvo que se pacte expresamente lo contrario. El impago de una mensualidad puede dar lugar a la suspensión del servicio mensual (no del proyecto ya entregado) hasta su regularización. Cualquier cambio de precio de estos servicios mensuales se comunicará con al menos 30 días de antelación.',
    'Cualquier modificación posterior del precio, el alcance o los plazos se formaliza mediante una nueva versión de este presupuesto, que requiere una nueva aceptación por el cliente.',
    'Esta propuesta tiene una validez de 15 días naturales desde su emisión, salvo que se indique un plazo distinto.',
    'Los importes indicados están sujetos al IVA (u otros impuestos aplicables) al tipo vigente en el momento de la facturación.',
]

CONDITIONS_BUSINESS = _COMMON_CONDITIONS + [
    'Responsabilidad de Web-Impulsa: queda limitada al daño directo y probado causado por un incumplimiento culpable de Web-Impulsa. En la medida permitida por la ley, el importe total de dicha responsabilidad se limita al importe efectivamente pagado por el cliente en el pedido concreto, quedando excluidos los daños indirectos y el lucro cesante. No se excluye la responsabilidad que la ley no permita limitar (dolo o negligencia grave). Como condición previa a cualquier reclamación, el cliente deberá notificar el problema por escrito a Web-Impulsa y concederle un plazo razonable para su subsanación.',
    'Legislación aplicable: legislación española. Para cualquier controversia, ambas partes se someten a los Juzgados y Tribunales de Barakaldo (Bizkaia), salvo que la normativa aplicable disponga otro fuero de forma imperativa.',
]

CONDITIONS_CONSUMER = _COMMON_CONDITIONS + [
    'Derecho de desistimiento: al tratarse de un contrato de prestación de servicios celebrado a distancia, dispones de un plazo de 14 días naturales desde la aceptación de esta propuesta para desistir del contrato sin necesidad de justificación, conforme al art. 102 y siguientes del Real Decreto Legislativo 1/2007 (TRLGDCU). Si solicitas expresamente que los trabajos comiencen antes de que finalice ese plazo, y el servicio llega a ejecutarse completamente, perderás tu derecho de desistimiento (art. 103.a TRLGDCU) — esta circunstancia se recoge de forma separada mediante un consentimiento expreso adicional, y no se presume.',
    'Responsabilidad de Web-Impulsa: queda limitada al daño directo y probado causado por un incumplimiento culpable de Web-Impulsa, sin que ello afecte a los derechos y garantías que la normativa de consumo reconoce de forma irrenunciable. Como condición previa a cualquier reclamación, deberás notificar el problema por escrito a Web-Impulsa y concederle un plazo razonable para su subsanación.',
    'Legislación aplicable: legislación española. Para cualquier controversia, y sin perjuicio de otros fueros que puedan corresponderte legalmente, serán competentes los Juzgados y Tribunales de tu domicilio como consumidor (art. 90.2 TRLGDCU, derecho irrenunciable).',
]

# Backward-compatible default used when a draft proposal is first created (antes de
# que el cliente elija su tipo en el portal) y como último recurso en el PDF si
# `proposal.conditions` viniera vacío. Se sobrescribe con la variante correcta
# (CONSUMER/BUSINESS) en el momento de la aceptación.
CONDITIONS = CONDITIONS_BUSINESS

# ── Checkboxes de consentimiento del formulario de aceptación ─────────────────
CONSENT_LABELS = {
    'tax_data': 'Declaro que los datos fiscales indicados (nombre/razón social, NIF/NIE/CIF, domicilio fiscal) son correctos, completos y son los que deben figurar en la factura.',
    'scope':    'He leído y acepto el alcance del proyecto, lo que NO está incluido (exclusiones) y los plazos de entrega indicados en esta propuesta.',
    'price':    'He revisado el desglose del presupuesto (base imponible, IVA y total) y estoy de acuerdo con el precio final.',
    'payment':  'Acepto la forma de pago seleccionada y el calendario de pagos indicado.',
    'hosting':  'Acepto las condiciones de hosting, dominio y soporte/mantenimiento incluidas en esta propuesta, en su caso.',
    'privacy':  'He leído la información sobre protección de datos personales y acepto el tratamiento de mis datos conforme a lo indicado.',
}

# Checkbox adicional, solo para client_type == 'particular'
WITHDRAWAL_CONSENT_TEXT = (
    'Solicito expresamente que el servicio comience antes de que finalice el plazo legal de '
    'desistimiento de 14 días naturales, y entiendo que, una vez el servicio se haya ejecutado '
    'completamente, perderé mi derecho a desistir del contrato (art. 103.a del Real Decreto '
    'Legislativo 1/2007).'
)
