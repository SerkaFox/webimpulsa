"""
Configuración del chequeo digital — versión, categorías, coeficientes y las
~11 preguntas puntuables con su texto por sector. Editar aquí basta para
cambiar el cuestionario; `scoring.py` no tiene ningún texto ni número
hardcodeado aparte de lo que vive en este módulo.
"""

QUESTIONNAIRE_VERSION = 'v1-2026-07'

# 'no_aplica' se excluye siempre del denominador — no tiene coeficiente.
COEFFICIENTS = {
    'si': 1.0,
    'en_parte': 0.5,
    'no_se': 0.25,
    'no': 0.0,
}

ANSWER_OPTIONS = [
    {'value': 'si', 'label': 'Sí'},
    {'value': 'en_parte', 'label': 'En parte'},
    {'value': 'no_se', 'label': 'No estoy segura/o'},
    {'value': 'no', 'label': 'No'},
    {'value': 'no_aplica', 'label': 'No aplica'},
]

# Suman 100 — validado en tests (Etapa 8) y con una comprobación manual ahora.
CATEGORY_WEIGHTS = {
    'visibilidad': 15,
    'informacion': 15,
    'contacto': 15,
    'conversion': 20,
    'confianza': 10,
    'organizacion': 15,
    'fidelizacion': 10,
}

CATEGORY_LABELS = {
    'visibilidad': 'Visibilidad',
    'informacion': 'Información',
    'contacto': 'Contacto',
    'conversion': 'Reserva / Pedido / Conversión',
    'confianza': 'Confianza',
    'organizacion': 'Organización y automatización',
    'fidelizacion': 'Fidelización y medición',
}

# Referencia por sector — configurable, 75 es el valor por defecto histórico.
SECTOR_BENCHMARKS = {
    'salon': 75,
    'bar': 75,
    'taller': 70,
    'academia': 75,
    'clinica': 78,
    'tienda': 72,
    'inmobiliaria': 75,
    'otro': 75,
}

# Las 11 preguntas puntuables. `applies_to` limitado = solo se pregunta/puntúa
# en esos sectores (si se omite, aplica a todos). `text_by_sector` siempre
# tiene '_default'; los sectores con matiz propio tienen su propia clave.
QUESTIONS = [
    {
        'id': 'gbp_accuracy',
        'category': 'visibilidad',
        'hint': 'Es lo primero que ve un cliente cuando te busca en el mapa de Google.',
        'text_by_sector': {
            '_default': '¿Tu ficha de Google (la que aparece en el mapa cuando te buscan) tiene el '
                        'horario, teléfono, dirección y fotos actualizados?',
            'bar': '¿Tu ficha de Google tiene el horario, teléfono, dirección y fotos del local y '
                   'los platos actualizados?',
            'salon': '¿Tu ficha de Google tiene el horario, teléfono, dirección y fotos de tus '
                      'trabajos actualizados?',
            'taller': '¿Tu ficha de Google tiene el horario, teléfono, dirección y fotos del taller '
                       'actualizados?',
            'clinica': '¿Tu ficha de Google tiene el horario, teléfono, dirección y fotos de la '
                        'consulta actualizados?',
            'tienda': '¿Tu ficha de Google tiene el horario, teléfono, dirección y fotos de la '
                       'tienda actualizados?',
            'academia': '¿Tu ficha de Google tiene el horario, teléfono, dirección y fotos del '
                         'centro actualizados?',
        },
        'good': 'Tu ficha de Google está completa y actualizada.',
        'fix': 'Actualizar tu ficha de Google: horario, teléfono, dirección y fotos.',
    },
    {
        'id': 'mobile_page',
        'category': 'informacion',
        'hint': 'La mayoría de tus clientes te van a mirar desde el móvil, no desde un ordenador.',
        'text_by_sector': {
            '_default': '¿Tienes una página o canal propio que se vea bien y sea fácil de usar '
                        'desde el móvil?',
        },
        'good': 'Tienes un canal propio que funciona bien en el móvil.',
        'fix': 'Tener una página o canal propio que se vea y use bien desde el móvil.',
    },
    {
        'id': 'catalog_visible',
        'category': 'informacion',
        'hint': 'Sin sorpresas: el cliente sabe qué esperar antes de escribirte.',
        'text_by_sector': {
            '_default': '¿Se ven tus servicios y al menos un precio orientativo sin tener que '
                        'preguntar?',
            'bar': '¿Un cliente puede ver tu carta y los precios (o un rango orientativo) sin '
                   'tener que preguntarte?',
            'salon': '¿Se ven tus servicios y precios orientativos sin tener que preguntar?',
            'clinica': '¿Se ven tus servicios o especialidades y al menos un precio orientativo sin '
                        'tener que preguntar?',
            'taller': '¿Se explica con claridad qué tipo de reparaciones o servicios ofreces?',
            'tienda': '¿Un cliente puede ver tus productos y precios (o un rango orientativo) sin '
                       'tener que preguntarte?',
            'academia': '¿Se ven tus cursos, horarios y precios sin tener que preguntar?',
            'inmobiliaria': '¿Se ven con claridad los servicios que ofreces (zonas, tipo de '
                             'propiedades o trabajos)?',
        },
        'good': 'Tus servicios y precios orientativos se ven con claridad.',
        'fix': 'Mostrar con más claridad tus servicios y al menos un precio orientativo.',
    },
    {
        'id': 'one_tap_contact',
        'category': 'contacto',
        'hint': 'Cuantos menos pasos, más fácil es que te escriban.',
        'text_by_sector': {
            '_default': '¿Un cliente puede escribirte por WhatsApp, llamarte o rellenar un '
                        'formulario con un solo toque, sin tener que buscar el número?',
        },
        'good': 'Un cliente puede contactarte con un solo toque.',
        'fix': 'Añadir un botón de contacto directo (WhatsApp, llamada o formulario) con un solo toque.',
    },
    {
        'id': 'main_action_no_wait',
        'category': 'conversion',
        'hint': 'Que pueda hacer lo principal ya, sin esperar a que alguien le conteste.',
        'text_by_sector': {
            '_default': '¿Puede pedir lo que necesita (reservar, comprar, solicitar presupuesto) '
                        'sin esperar a que le llamen?',
            'bar': '¿Puede reservar mesa sin tener que esperar a que le devuelvan la llamada?',
            'salon': '¿Puede pedir cita eligiendo día y hora sin esperar respuesta?',
            'clinica': '¿Puede pedir cita eligiendo día y hora sin esperar respuesta?',
            'taller': '¿Puede pedir presupuesto o dejar su vehículo sin esperar a que le llamen?',
            'tienda': '¿Puede comprar o reservar el producto sin esperar respuesta?',
            'academia': '¿Puede inscribirse o pedir plaza sin esperar respuesta?',
            'inmobiliaria': '¿Puede solicitar presupuesto o visita sin esperar respuesta?',
        },
        'good': 'El cliente puede completar la acción principal sin esperar.',
        'fix': 'Permitir completar la acción principal (reservar/pedir/solicitar) sin esperar respuesta.',
    },
    {
        'id': 'messages_lost',
        'category': 'contacto',
        'hint': 'Un mensaje sin respuesta a tiempo es un cliente que se va a otro sitio.',
        'text_by_sector': {
            '_default': '¿Sabes con seguridad quién revisa los mensajes y en cuánto tiempo sueles '
                        'responder?',
        },
        'good': 'Sabes quién responde y en cuánto tiempo.',
        'fix': 'Definir quién revisa los mensajes y en cuánto tiempo se responde.',
    },
    {
        'id': 'auto_confirmation',
        'category': 'organizacion',
        'hint': 'Un aviso automático reduce muchísimo las ausencias y las dudas de última hora.',
        'text_by_sector': {
            '_default': '¿Envías alguna confirmación o recordatorio automático a tus clientes?',
            'bar': '¿Envías confirmación automática de la reserva y un recordatorio antes?',
            'salon': '¿Envías un recordatorio automático antes de la cita?',
            'clinica': '¿Envías un recordatorio automático antes de la cita?',
            'taller': '¿Avisas automáticamente cuando el vehículo está listo?',
            'tienda': '¿Confirmas automáticamente los pedidos o reservas de producto?',
            'academia': '¿Envías un recordatorio automático de la próxima clase?',
            'inmobiliaria': '¿Confirmas automáticamente la recepción de una solicitud o visita?',
        },
        'good': 'Ya envías confirmaciones o recordatorios automáticos.',
        'fix': 'Activar confirmaciones o recordatorios automáticos.',
    },
    {
        'id': 'reviews_uptodate',
        'category': 'confianza',
        'hint': 'La opinión de otros clientes genera confianza al instante.',
        'text_by_sector': {
            '_default': '¿Tienes reseñas y fotos recientes, y respondes a las reseñas que recibes?',
        },
        'good': 'Tus reseñas y fotos son recientes, y respondes a ellas.',
        'fix': 'Reunir reseñas y fotos recientes, y responder a las que recibas.',
    },
    {
        'id': 'centralized_records',
        'category': 'organizacion',
        'hint': 'Así no se pierde ni se duplica nada entre cuadernos, chats y hojas de cálculo.',
        'text_by_sector': {
            '_default': '¿Tus reservas, pedidos, citas o trabajos están en un solo sitio, o '
                        'repartidos entre cuadernos, WhatsApp y Excel?',
        },
        'good': 'Tienes tus reservas/pedidos/citas centralizados en un solo sitio.',
        'fix': 'Centralizar reservas, pedidos, citas o trabajos en un solo sitio.',
    },
    {
        'id': 'repetitive_tasks',
        'category': 'organizacion',
        'hint': 'Lo que se repite cada día a mano casi siempre se puede automatizar.',
        'text_by_sector': {
            '_default': '¿Hay tareas que repites cada día a mano (confirmar, recordar, hacer '
                        'seguimiento) que podrían hacerse solas?',
        },
        'good': 'Ya tienes automatizadas tus tareas repetitivas del día a día.',
        'fix': 'Automatizar las tareas repetitivas que hoy haces a mano cada día.',
    },
    {
        'id': 'brings_back_customers',
        'category': 'fidelizacion',
        'hint': 'Que un cliente vuelva suele costar mucho menos que conseguir uno nuevo.',
        'text_by_sector': {
            '_default': '¿Tienes alguna forma de que un cliente vuelva (aviso, oferta, recordatorio) '
                        'y sabes cómo te encontró la primera vez?',
        },
        'good': 'Tienes forma de traer de vuelta a tus clientes y sabes de dónde vienen.',
        'fix': 'Añadir una forma sencilla de traer de vuelta a tus clientes y de saber de dónde vienen.',
    },
]
