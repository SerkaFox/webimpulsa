"""Ayuda contextual mostrada en el modal "❓".

TASK_GUIDANCE da una guía específica por título exacto de tarea (más útil que una
guía genérica de categoría, porque "Yoga / Estiramientos" y "Tiempo en familia"
necesitan consejos muy distintos aunque compartan categoría "personal").
CATEGORY_GUIDANCE se mantiene como respaldo para tareas personalizadas (custom_title)
que no están en el catálogo y por tanto no tienen guía específica."""

CATEGORY_GUIDANCE = {
    'ventas': {
        'label': 'Ventas y prospección',
        'description': 'Tareas para conseguir y avanzar clientes: contactar, presentar, negociar y cerrar.',
        'tips': [
            'Define el objetivo del contacto antes de escribir o llamar.',
            'Prepara un guion breve con 2-3 puntos clave.',
            'Cierra siempre con un siguiente paso concreto y una fecha.',
            'Registra el resultado en el reporte para no perder el hilo.',
        ],
    },
    'contenido': {
        'label': 'Contenido y marketing',
        'description': 'Tareas de creación y publicación de contenido para atraer y educar a tu audiencia.',
        'tips': [
            'Define el mensaje central antes de escribir.',
            'Usa un gancho claro en las primeras dos líneas.',
            'Incluye siempre una llamada a la acción.',
            'Reutiliza el mismo contenido en varios formatos.',
            'Revisa el alcance a los pocos días de publicar.',
        ],
    },
    'estrategia': {
        'label': 'Estrategia y negocio',
        'description': 'Tareas de pensar y organizar el negocio: procesos, ofertas y decisiones importantes.',
        'tips': [
            'Bloquea tiempo sin interrupciones para esto.',
            'Escribe el objetivo en una sola frase antes de empezar.',
            'Sal con una lista de 2-3 pasos concretos, no solo ideas.',
            'Revisa qué funcionó la semana pasada antes de cambiar de rumbo.',
        ],
    },
    'finanzas': {
        'label': 'Finanzas',
        'description': 'Tareas de control económico: precios, cobros, facturación y orden de cuentas.',
        'tips': [
            'Usa siempre la misma hoja o app para registrar todo.',
            'Anota cada ingreso o gasto el mismo día, no lo dejes acumular.',
            'Revisa márgenes reales antes de bajar un precio.',
            'Aparta un porcentaje fijo para impuestos en cuanto cobres.',
        ],
    },
    'perfil': {
        'label': 'Marca personal',
        'description': 'Tareas para cuidar cómo te perciben: perfiles, imagen y reputación profesional.',
        'tips': [
            'Cuida que la foto y el titular estén siempre actualizados.',
            'Escribe una bio corta con tu propuesta de valor, no solo tu cargo.',
            'Pide una recomendación o testimonio de vez en cuando.',
            'Mantén el mismo tono y colores en todos tus perfiles.',
        ],
    },
    'personal': {
        'label': 'Día personal',
        'description': 'Tiempo para ti: descanso, familia y desconexión. Tan planificado e importante como el trabajo.',
        'tips': [
            'Evita pantallas los primeros minutos al empezar.',
            'Sal al aire libre si puedes, aunque sean 10 minutos.',
            'Hazlo sin culpa — también es parte del plan.',
        ],
    },
    'habito': {
        'label': 'Hábito diario',
        'description': 'Hábitos obligatorios que sostienen todo lo demás: cuerpo, mente e idioma.',
        'tips': [
            'Hazlo siempre a la misma hora para que se vuelva automático.',
            'Empieza más pequeño de lo que crees necesario si un día cuesta.',
            'Márcalo como hecho en cuanto lo termines, no lo dejes para luego.',
        ],
    },
    'cierre': {
        'label': 'Cierre de mes',
        'description': 'Tareas de cierre: revisar, celebrar y preparar el mes siguiente.',
        'tips': [
            'Celebra lo logrado antes de mirar lo pendiente.',
            'Anota al menos una lección aprendida del mes.',
            'Prepara el plan del mes siguiente con datos reales, no solo intención.',
        ],
    },
}

# ── Enlaces reutilizables (URLs reales y seguras: no vídeos concretos inventados,
# salvo el de yoga, verificado por búsqueda) ──
LINK_LINKEDIN_FEED = {'label': 'Abrir LinkedIn para publicar', 'url': 'https://www.linkedin.com/feed/'}
LINK_LINKEDIN_SEARCH = {'label': 'Buscar empresas/contactos en LinkedIn', 'url': 'https://www.linkedin.com/search/results/all/'}


def _yt(query):
    from urllib.parse import quote
    return {'label': f'Buscar en YouTube: {query}', 'url': f'https://www.youtube.com/results?search_query={quote(query)}'}


# ── Guía específica por tarea (clave = título exacto en TaskCatalogItem) ──
TASK_GUIDANCE = {

    # ── VENTAS ──
    'Analizar clientes actuales': {
        'description': 'Revisar tu cartera actual para detectar quién puede ampliar servicio, quién está en riesgo y quién puede darte referidos.',
        'tips': [
            'Haz una lista con cada cliente activo y su nivel de satisfacción (alto/medio/bajo).',
            'Marca a los que llevan más de 2 meses sin contacto — son prioridad.',
            'Anota una oportunidad de ampliación concreta por cliente, aunque no la ejecutes hoy.',
        ],
    },
    'Investigar a 3 empresas': {
        'description': 'Investigación previa antes de contactar: sin esto, cualquier mensaje suena genérico.',
        'tips': [
            'Mira su web, LinkedIn y redes: ¿qué venden, a quién, cómo se comunican?',
            'Busca una señal reciente (lanzamiento, contratación, evento) para usar de gancho.',
            'Anota el nombre de la persona correcta a contactar, no solo "la empresa".',
        ],
        'links': [LINK_LINKEDIN_SEARCH],
    },
    'Contactar 2 empresas': {
        'description': 'Primer contacto frío o cálido con una empresa concreta.',
        'tips': [
            'Personaliza la primera línea con algo específico de ellos.',
            'Sé breve: 4-5 líneas máximo, un único objetivo por mensaje.',
            'Propón un paso pequeño (una llamada de 15 min), no "trabajar juntos".',
        ],
    },
    'Presentación comercial': {
        'description': 'Reunión o llamada donde presentas tu servicio a un cliente potencial.',
        'tips': [
            'Empieza preguntando por su situación antes de hablar de tu servicio.',
            'Usa máximo 5-6 diapositivas o puntos si es una presentación formal.',
            'Termina siempre con una pregunta concreta o una propuesta de siguiente paso.',
        ],
        'links': [_yt('cómo hacer una presentación comercial efectiva')],
    },
    'Propuesta de valor clara': {
        'description': 'Definir en una frase qué resuelves, para quién y por qué eres distinta.',
        'tips': [
            'Fórmula útil: "Ayudo a [quién] a conseguir [resultado] sin [dolor habitual]".',
            'Pruébala en voz alta con alguien que no conozca tu negocio — si no lo entiende, simplifica.',
            'Evita adjetivos vacíos ("profesional", "de calidad"); usa resultados concretos.',
        ],
    },
    'Enviar 3 propuestas': {
        'description': 'Envío de propuestas económicas/comerciales ya preparadas a clientes potenciales.',
        'tips': [
            'Revisa que cada propuesta tenga precio, alcance y plazo claros.',
            'Adjunta o enlaza 1 ejemplo de trabajo similar si puedes.',
            'Anota en tu calendario el día de seguimiento (a los 3-4 días).',
        ],
    },
    'Seguimiento clientes': {
        'description': 'Retomar contacto con clientes o leads que quedaron a medias.',
        'tips': [
            'Ordena por antigüedad: contacta primero a los que llevan más tiempo esperando.',
            'Aporta algo nuevo en el mensaje (no solo "¿alguna novedad?"): un dato, una idea, un caso.',
            'Si no responden tras 2 seguimientos, cierra el lead como "en pausa" y sigue adelante.',
        ],
    },
    'Reunión estratégica': {
        'description': 'Reunión con un cliente o socio para revisar el rumbo de la colaboración, no el día a día operativo.',
        'tips': [
            'Prepara 3 preguntas abiertas sobre sus objetivos a medio plazo.',
            'Lleva 1-2 datos o resultados para sustentar la conversación.',
            'Sal con al menos un acuerdo o acción concreta, no solo buenas sensaciones.',
        ],
    },
    'Detectar necesidades': {
        'description': 'Conversación exploratoria para entender el problema real del cliente antes de ofrecer nada.',
        'tips': [
            'Pregunta "¿por qué?" al menos dos veces sobre lo primero que te cuenten.',
            'Escucha más de lo que hablas: apunta literalmente sus palabras.',
            'No propongas solución en esta llamada — solo entiende el problema.',
        ],
    },
    'Preparar propuesta': {
        'description': 'Redactar una propuesta comercial a medida antes de enviarla.',
        'tips': [
            'Empieza resumiendo el problema del cliente con sus propias palabras.',
            'Sé específica en alcance y entregables — evita ambigüedad ("varias publicaciones").',
            'Incluye una validez de la oferta (ej. 15 días) para dar sensación de urgencia sana.',
        ],
    },
    'Establecer precios claros': {
        'description': 'Definir o revisar tu tabla de precios para que sea fácil de comunicar y de cobrar.',
        'tips': [
            'Calcula tu coste real por hora antes de poner un precio de paquete.',
            'Ten 2-3 paquetes cerrados en vez de precio "a medida" para todo.',
            'Escribe el precio en algún sitio (web, PDF) — la opacidad genera fricción.',
        ],
    },
    'Llamadas de seguimiento': {
        'description': 'Llamadas cortas para retomar el contacto con un lead o cliente que ya te conoce.',
        'tips': [
            'Ten 1 motivo concreto para llamar, no solo "saber cómo va".',
            'Prepara qué dirás en los primeros 10 segundos.',
            'Anota el resultado y la próxima fecha de contacto al colgar.',
        ],
    },
    'Crear alianza estratégica': {
        'description': 'Buscar o formalizar una colaboración con otro profesional o negocio complementario (no competidor).',
        'tips': [
            'Piensa en quién ya tiene la confianza de tu cliente ideal (ej. diseñadoras, gestorías).',
            'Propón algo concreto y de beneficio mutuo (referidos cruzados, pack conjunto).',
            'Empieza con una colaboración pequeña antes de un acuerdo formal grande.',
        ],
    },
    'Contactar 3 potenciales': {
        'description': 'Primer contacto con 3 clientes potenciales nuevos.',
        'tips': [
            'Usa canales distintos si puedes (email, LinkedIn, WhatsApp) según cada perfil.',
            'Personaliza al menos la primera frase de cada mensaje.',
            'Un único objetivo por mensaje: agendar una llamada, no "vender" ya.',
        ],
    },
    'Analizar competencia': {
        'description': 'Revisar qué hacen otras profesionales/negocios similares para detectar huecos y aprender.',
        'tips': [
            'Mira precios, servicios y cómo se comunican en redes/web.',
            'Busca qué NO están ofreciendo — ahí puede estar tu diferencia.',
            'No copies el tono; usa lo que veas solo como referencia de mercado.',
        ],
        'links': [LINK_LINKEDIN_SEARCH],
    },
    'Networking online': {
        'description': 'Conectar y conversar con otras profesionales en comunidades o redes (no vender directamente).',
        'tips': [
            'Comenta de forma genuina en 3-5 publicaciones de tu sector antes de escribir en privado.',
            'Preséntate con una frase clara sobre a quién ayudas.',
            'Prioriza calidad de conversación sobre cantidad de contactos añadidos.',
        ],
        'links': [LINK_LINKEDIN_FEED],
    },
    'Propuesta de colaboración': {
        'description': 'Propuesta formal a otro profesional o empresa para colaborar (alianza, referidos, proyecto conjunto).',
        'tips': [
            'Explica primero qué gana la otra parte, no solo qué necesitas tú.',
            'Propón algo concreto y fácil de aceptar (una prueba pequeña) antes de un compromiso grande.',
        ],
    },
    'Negociar proyectos': {
        'description': 'Conversación de negociación de alcance, precio o plazos con un cliente.',
        'tips': [
            'Define antes de la llamada tu límite mínimo aceptable.',
            'Si bajas precio, quita alcance — nunca regales trabajo extra gratis.',
            'Deja pausas de silencio tras proponer una cifra; no rellenes el silencio tú misma.',
        ],
    },
    'Cerrar acuerdos': {
        'description': 'Formalizar un acuerdo ya negociado (firma, confirmación, primer pago).',
        'tips': [
            'Ten listo el documento o presupuesto formal antes de la llamada de cierre.',
            'Pide la confirmación explícita ("¿avanzamos entonces?"), no la des por hecha.',
            'Define el primer paso concreto tras el cierre (fecha de inicio, primer pago).',
        ],
    },
    'Detectar oportunidades': {
        'description': 'Explorar el mercado o tu red para encontrar posibles nuevos clientes o proyectos.',
        'tips': [
            'Revisa quién ha interactuado contigo en redes últimamente sin convertirse en cliente.',
            'Pregunta a 1-2 clientes actuales si conocen a alguien que pueda necesitarte.',
        ],
    },
    'Llamadas de prospección': {
        'description': 'Llamadas en frío o semi-frío a contactos nuevos para generar interés.',
        'tips': [
            'Prepara un guion de apertura de 15 segundos, ensayado en voz alta.',
            'El objetivo de la llamada es agendar, no cerrar venta en el mismo momento.',
            'Registra cada llamada (contestó/no contestó/interesado) para medir tu ratio.',
        ],
    },
    'Propuesta personalizada': {
        'description': 'Propuesta hecha a medida para un cliente concreto, no una plantilla genérica.',
        'tips': [
            'Menciona 1-2 detalles específicos de su negocio dentro de la propuesta.',
            'Ajusta el alcance a lo que realmente necesita, no a tu paquete estándar.',
        ],
    },
    'Delegar tareas': {
        'description': 'Identificar tareas que puedes pasar a otra persona (colaboradora, freelance, herramienta) para liberar tu tiempo.',
        'tips': [
            'Elige tareas repetitivas y bien definidas, no las que requieren tu criterio único.',
            'Documenta el paso a paso una vez — te ahorrará explicarlo cada vez.',
        ],
    },
    'Cerrar proyecto': {
        'description': 'Finalizar formalmente un proyecto con el cliente: entrega, balance y despedida profesional.',
        'tips': [
            'Confirma por escrito que todos los entregables están aceptados.',
            'Pide feedback y, si ha ido bien, un testimonio o referido.',
            'Cierra también internamente: factura final y archivo del proyecto.',
        ],
    },
    'Onboarding cliente': {
        'description': 'Recibir a un cliente nuevo: explicar el proceso, expectativas y primeros pasos.',
        'tips': [
            'Ten una checklist o documento de bienvenida reutilizable.',
            'Aclara desde el inicio qué necesitas de ellos y en qué plazos.',
            'Agenda ya la primera fecha de seguimiento, no la dejes "para más adelante".',
        ],
    },
    'Evaluar resultados': {
        'description': 'Revisar qué ha funcionado (o no) en ventas/proyectos recientes.',
        'tips': [
            'Compara resultado real contra lo esperado, con números si es posible.',
            'Anota 1 cosa a repetir y 1 cosa a cambiar, no solo "fue bien/mal".',
        ],
    },
    'Analizar resultados': {
        'description': 'Revisión de resultados generales (ventas, proyectos, métricas) para decidir próximos pasos.',
        'tips': [
            'Usa siempre los mismos indicadores para poder comparar mes a mes.',
            'Prioriza 2-3 conclusiones accionables sobre una lista larga de datos.',
        ],
    },
    'Definir próximos pasos': {
        'description': 'Cerrar una tarea de análisis o revisión con acciones concretas para seguir avanzando.',
        'tips': [
            'Escribe cada paso como una acción con verbo y fecha, no como una idea abierta.',
            'Limita a 3 próximos pasos máximo — más que eso no se ejecuta.',
        ],
    },
    'Prueba admin': {
        'description': 'Tarea de prueba interna, sin guía específica necesaria.',
        'tips': ['Tarea de prueba del sistema — puedes ignorarla o eliminarla.'],
    },

    # ── CONTENIDO ──
    'Publicar post en LinkedIn': {
        'description': 'Publicar un post en tu perfil de LinkedIn para dar visibilidad a tu marca personal.',
        'tips': [
            'Elige un único tema: un aprendizaje, un caso real o una opinión con criterio.',
            'Primera línea = gancho: debe funcionar sola, antes del "ver más".',
            'Escribe en párrafos cortos (1-2 líneas) y termina con una pregunta o CTA.',
            'Publica en horario laboral entre semana (mejor martes-jueves por la mañana).',
        ],
        'links': [LINK_LINKEDIN_FEED],
    },
    'Publicar en LinkedIn': {
        'description': 'Publicar contenido en tu perfil o página de LinkedIn.',
        'tips': [
            'Elige un tema con el que ayudes a tu cliente ideal, no solo que hable de ti.',
            'Usa una historia o ejemplo concreto en vez de consejos genéricos.',
            'Responde los comentarios en la primera hora — mejora el alcance.',
        ],
        'links': [LINK_LINKEDIN_FEED],
    },
    'Publicar en blog/LinkedIn': {
        'description': 'Publicar una entrada de blog y/o compartirla en LinkedIn.',
        'tips': [
            'Escribe primero para resolver una duda concreta de tu cliente ideal.',
            'Si lo compartes en LinkedIn, no pegues el enlace en el post principal — ponlo en el primer comentario, así el algoritmo lo distribuye mejor.',
        ],
        'links': [LINK_LINKEDIN_FEED],
    },
    'Captar leads en LinkedIn': {
        'description': 'Buscar y contactar activamente con potenciales clientes dentro de LinkedIn.',
        'tips': [
            'Usa el buscador con filtros de sector/cargo/ubicación antes de escribir a nadie.',
            'Personaliza la nota de conexión — nunca copies/pegues el mismo mensaje a todos.',
            'Aporta valor en el primer mensaje (un dato, una idea) antes de proponer nada.',
        ],
        'links': [LINK_LINKEDIN_SEARCH],
    },
    'Crear contenido de valor': {
        'description': 'Crear contenido educativo o útil (no promocional) para tu audiencia.',
        'tips': [
            'Parte de una pregunta real que te hayan hecho clientes o seguidoras.',
            'Da un consejo aplicable ya, no solo teoría general.',
            'Cierra invitando a comentar su propia experiencia — sube el alcance.',
        ],
    },
    'Publicar en redes sociales': {
        'description': 'Publicación de contenido en tus redes (Instagram, Facebook, etc.).',
        'tips': [
            'Adapta el formato a la red (vídeo corto en Reels/TikTok, imagen + texto en Facebook).',
            'Usa 3-5 hashtags relevantes, no genéricos masivos.',
            'Programa la publicación en tu mejor horario según tus estadísticas.',
        ],
    },
    'Publicar en redes': {
        'description': 'Publicación de contenido en redes sociales.',
        'tips': [
            'Ten un tema claro por publicación — no mezcles varios mensajes en uno.',
            'Incluye siempre una llamada a la acción (comentar, guardar, escribir).',
        ],
    },
    'Email marketing (envío)': {
        'description': 'Envío de una campaña o newsletter a tu lista de contactos.',
        'tips': [
            'Un único objetivo por email (leer un artículo, reservar una llamada, comprar).',
            'Asunto corto y concreto — evita mayúsculas y signos de exclamación excesivos.',
            'Revisa el enlace y el envío de prueba a ti misma antes de disparar a toda la lista.',
        ],
    },
    'Email marketing (valor)': {
        'description': 'Redactar un email centrado en aportar valor (no venta directa) a tu lista.',
        'tips': [
            'Comparte un aprendizaje, caso o recurso útil de verdad, no solo novedades tuyas.',
            'Escribe como si fuera a una sola persona, en tono cercano.',
        ],
    },
    'Analizar métricas': {
        'description': 'Revisar el rendimiento de tu contenido/campañas (alcance, clics, conversiones).',
        'tips': [
            'Compara siempre contra tu propia media, no contra cifras ajenas.',
            'Identifica el contenido con mejor resultado del mes y piensa por qué funcionó.',
            'Anota 1 cambio a probar el mes que viene basado en los datos.',
        ],
    },
    'Testimonios / Pruebas': {
        'description': 'Recopilar testimonios o pruebas sociales de clientes satisfechas.',
        'tips': [
            'Pide el testimonio justo después de un buen resultado, cuando el cliente está más contento.',
            'Facilita el trabajo: envía 2-3 preguntas guía en vez de "escribe lo que quieras".',
            'Pide permiso explícito para usar su nombre/foto/logo en tu web o redes.',
        ],
    },
    'Publicar testimonio': {
        'description': 'Publicar un testimonio de cliente ya recopilado en tu web o redes.',
        'tips': [
            'Acompáñalo de contexto (qué problema tenía, qué resultado obtuvo).',
            'Usa el nombre/foto real si tienes permiso — genera mucha más confianza que uno anónimo.',
        ],
    },
    'Mejorar landing page': {
        'description': 'Revisar y mejorar una página de aterrizaje (oferta, servicio, lead magnet).',
        'tips': [
            'Comprueba que el titular dice el resultado, no solo el nombre del servicio.',
            'Un único CTA claro y repetido, no varios botones distintos compitiendo.',
            'Añade prueba social (testimonio, logo, cifra) cerca del botón de acción.',
        ],
    },
    'Crear contenido (vídeo)': {
        'description': 'Grabar un vídeo para redes, web o formación — la tarea con más partes técnicas: guion, cámara y grabación.',
        'tips': [
            'Escribe un guion breve con 3 puntos: gancho (5s), contenido, cierre con CTA.',
            'Cámara a la altura de los ojos, luz de frente (nunca a contraluz de una ventana).',
            'Graba en horizontal para web/YouTube y vertical para Reels/TikTok — no reutilices el mismo encuadre para ambos.',
            'Ensaya el guion en voz alta 1-2 veces antes de grabar la toma buena; no busques la perfección a la primera.',
            'Usa el móvil apoyado (trípode o pila de libros) para evitar que tiemble la imagen.',
        ],
        'links': [
            _yt('cómo grabar vídeos con el móvil para redes sociales'),
            _yt('cómo escribir guion para vídeo corto'),
        ],
    },
    'Preparar contenido': {
        'description': 'Planificación/preparación de contenido antes de crearlo o publicarlo (calendario, temas, guiones).',
        'tips': [
            'Define 3-4 temas del mes en base a las dudas frecuentes de tus clientes.',
            'Prepara varios contenidos de una sentada (batching) en vez de improvisar cada día.',
        ],
    },
    'Crear guía / Recurso': {
        'description': 'Crear un recurso descargable (guía, checklist, plantilla) para captar leads o aportar valor.',
        'tips': [
            'Que resuelva un problema muy concreto y pequeño, no "todo" sobre un tema.',
            'Cuida el diseño básico (tipografía legible, tu marca) aunque sea un PDF simple.',
        ],
    },
    'Crear plantilla / Recurso': {
        'description': 'Crear una plantilla reutilizable (documento, hoja de cálculo, checklist) para ti o para clientes.',
        'tips': [
            'Piensa en una tarea que repites cada mes — esa es la mejor candidata a plantilla.',
            'Déjala lista para reutilizar en 2 minutos la próxima vez, no desde cero.',
        ],
    },
    'Crear estudio de caso': {
        'description': 'Documentar un proyecto real con cliente como caso de éxito para mostrar resultados.',
        'tips': [
            'Estructura: situación inicial → qué hiciste → resultado con datos concretos.',
            'Pide permiso al cliente antes de publicar nombres o cifras.',
        ],
    },
    'Publicar caso de éxito': {
        'description': 'Publicar un caso de éxito ya preparado en redes, web o LinkedIn.',
        'tips': [
            'Lidera con el resultado (el titular), no con el proceso.',
            'Incluye una cifra o dato concreto si el cliente lo permite — genera más confianza que texto genérico.',
        ],
        'links': [LINK_LINKEDIN_FEED],
    },
    'Mejorar portfolio': {
        'description': 'Actualizar tu portfolio o muestra de trabajos con proyectos recientes.',
        'tips': [
            'Enseña 4-6 proyectos bien elegidos en vez de todo lo que has hecho.',
            'Para cada proyecto, añade una frase de contexto y resultado, no solo la imagen.',
        ],
    },
    'Webinar / Directo': {
        'description': 'Preparar o realizar una sesión en directo/webinar para tu audiencia.',
        'tips': [
            'Define un único resultado que la gente se lleve al terminar.',
            'Prepara 3-4 puntos guía, no lo leas todo — suena más natural en directo.',
            'Deja tiempo real para preguntas al final; ahí suele salir el mejor contenido.',
        ],
        'links': [_yt('cómo preparar un webinar paso a paso')],
    },
    'Taller / Formación': {
        'description': 'Preparar o impartir un taller/formación, propia o para tu audiencia.',
        'tips': [
            'Define el objetivo de aprendizaje en una frase antes de montar el contenido.',
            'Incluye un ejercicio práctico, no solo teoría — se recuerda mejor haciendo.',
        ],
    },

    # ── ESTRATEGIA ──
    'Prueba de sistema': {
        'description': 'Tarea de prueba interna, sin guía específica necesaria.',
        'tips': ['Tarea de prueba del sistema — puedes ignorarla o eliminarla.'],
    },
    'Definir objetivos semanales': {
        'description': 'Fijar los 2-3 objetivos que de verdad importan esta semana.',
        'tips': [
            'Escribe los objetivos en resultado ("cerrar 1 cliente"), no en actividad ("trabajar más").',
            'Limita a 3 objetivos — una lista larga no es una prioridad, es una lista de deseos.',
        ],
    },
    'Crear oferta irresistible': {
        'description': 'Diseñar o mejorar una oferta comercial muy atractiva y fácil de decidir.',
        'tips': [
            'Combina resultado claro + plazo + algo que reduzca el riesgo (garantía, prueba).',
            'Ponle nombre propio a la oferta — se recuerda y se comparte mejor que "mi servicio".',
        ],
    },
    'Estandarizar servicio 1': {
        'description': 'Documentar un servicio para que siempre se entregue igual, sin reinventarlo cada vez.',
        'tips': [
            'Escribe el paso a paso que sigues hoy, aunque sea informal — luego lo pules.',
            'Define qué está incluido y qué no, para evitar alcance ambiguo con clientes.',
        ],
    },
    'Mejorar web (1 ajuste)': {
        'description': 'Un único cambio concreto en tu web (no un rediseño completo).',
        'tips': [
            'Elige el ajuste con más impacto: titular, CTA principal o velocidad de carga.',
            'Compruébalo también en móvil — la mayoría del tráfico suele venir de ahí.',
        ],
    },
    'Mejorar automatizaciones': {
        'description': 'Revisar o crear una automatización que te ahorre trabajo repetitivo.',
        'tips': [
            'Empieza por la tarea manual que más se repite y menos criterio requiere.',
            'Prueba la automatización con un caso real antes de confiar en ella al 100%.',
        ],
    },
    'Optimizar procesos': {
        'description': 'Revisar un proceso interno para hacerlo más simple o rápido.',
        'tips': [
            'Dibuja el proceso actual paso a paso antes de intentar mejorarlo.',
            'Busca el paso que más tiempo consume — ahí está la mejora con más impacto.',
        ],
    },
    'Mejorar procesos internos': {
        'description': 'Ajustar cómo organizas tu trabajo interno (no de cara al cliente).',
        'tips': [
            'Cambia solo una cosa a la vez para poder ver si realmente mejora.',
            'Documenta el cambio para no volver al hábito anterior sin darte cuenta.',
        ],
    },
    'Plan de crecimiento': {
        'description': 'Definir o revisar el plan de crecimiento del negocio a medio plazo.',
        'tips': [
            'Parte de dónde estás hoy con datos reales, no de dónde te gustaría estar.',
            'Elige 1-2 palancas de crecimiento (no cinco a la vez) para los próximos meses.',
        ],
    },
    'Optimizar servicios': {
        'description': 'Revisar tu catálogo de servicios para simplificarlo o mejorarlo.',
        'tips': [
            'Elimina o fusiona servicios que casi nadie contrata.',
            'Asegúrate de que cada servicio tiene un precio y alcance claros.',
        ],
    },
    'Crear plan de agosto': {
        'description': 'Planificación específica del mes de agosto (vacaciones, ritmo distinto de clientes).',
        'tips': [
            'Decide con antelación tus días libres y comunícalos a clientes.',
            'Adapta expectativas de resultados — agosto suele tener menos respuesta del mercado.',
        ],
    },
    'Preparar campañas': {
        'description': 'Planificar una campaña de marketing o ventas con fecha de inicio y fin.',
        'tips': [
            'Define el objetivo numérico de la campaña antes de crear los contenidos.',
            'Ten un calendario simple con qué publicas/envías cada día de campaña.',
        ],
    },
    'Automatizar procesos': {
        'description': 'Implementar una automatización (email, recordatorio, plantilla) que sustituya trabajo manual.',
        'tips': [
            'Automatiza primero lo repetitivo y mecánico, nunca el trato personal con el cliente.',
            'Revisa el resultado la primera vez que se dispare sola, para pillar errores pronto.',
        ],
    },
    'Evaluación mensual': {
        'description': 'Revisión de cómo ha ido el mes en conjunto (ventas, contenido, finanzas, energía personal).',
        'tips': [
            'Usa siempre la misma plantilla de preguntas para poder comparar mes a mes.',
            'Termina con 1-2 decisiones concretas para el mes siguiente.',
        ],
    },
    'Presentación online': {
        'description': 'Presentación realizada por videollamada (cliente, taller o webinar).',
        'tips': [
            'Comprueba cámara, audio y luz 5 minutos antes de empezar.',
            'Comparte pantalla solo lo necesario — evita ventanas o pestañas de más abiertas.',
            'Ten un plan B si falla la conexión (enlace alternativo, número de teléfono).',
        ],
        'links': [_yt('cómo preparar una videollamada profesional')],
    },

    # ── FINANZAS ──
    'Orden financiero': {
        'description': 'Poner en orden tus cuentas: ingresos, gastos y pendientes de cobro/pago.',
        'tips': [
            'Revisa que todo lo cobrado y pagado del mes esté registrado.',
            'Identifica facturas pendientes de cobro y prográmales un recordatorio.',
        ],
    },
    'Facturación / Finanzas': {
        'description': 'Emitir facturas pendientes y revisar el estado financiero general.',
        'tips': [
            'Factura en cuanto entregues, no lo acumules para "cuando tengas un rato".',
            'Revisa que el IVA/IRPF aplicado sea correcto antes de enviar.',
        ],
    },
    'Facturación / Cobros': {
        'description': 'Emitir facturas y hacer seguimiento de cobros pendientes.',
        'tips': [
            'Manda un recordatorio educado a los 3-5 días de vencer un pago.',
            'Si un cliente se retrasa de forma repetida, revisa tu forma de pago o anticipo.',
        ],
    },
    'Revisión financiera': {
        'description': 'Revisar en detalle tus números del mes: márgenes, gastos fijos, rentabilidad.',
        'tips': [
            'Separa gastos fijos de variables para ver de verdad cuánto necesitas facturar al mes.',
            'Compara el margen real de cada servicio, no solo el total facturado.',
        ],
    },
    'Ajustar precios': {
        'description': 'Revisar y, si toca, subir o reestructurar tus precios.',
        'tips': [
            'Calcula primero tu coste/hora real antes de decidir cuánto subir.',
            'Aplica el nuevo precio a clientes nuevos primero; a los actuales avísales con antelación.',
        ],
    },

    # ── PERFIL ──
    'Optimizar perfil profesional': {
        'description': 'Mejorar tu perfil de LinkedIn u otra red profesional: foto, titular, "acerca de".',
        'tips': [
            'El titular debe decir a quién ayudas y con qué resultado, no solo tu puesto.',
            'Usa una foto reciente, con buena luz y fondo neutro.',
            'Actualiza el "Acerca de" cada vez que cambie tu oferta o posicionamiento.',
        ],
        'links': [{'label': 'Editar tu perfil de LinkedIn', 'url': 'https://www.linkedin.com/in/me/'}],
    },

    # ── HÁBITO ──
    'Ejercicio físico 20 min': {
        'description': 'Movimiento diario breve — no tiene que ser gimnasio, cualquier actividad física cuenta.',
        'tips': [
            'Elige algo que puedas repetir sin pensar mucho: caminar rápido, bici, rutina en casa.',
            'Prepara la ropa/espacio la noche anterior para quitar fricción.',
        ],
        'links': [_yt('rutina de ejercicio 20 minutos en casa')],
    },
    'Castellano 30 min': {
        'description': 'Práctica diaria de español — clave si estás en proceso de aprender/mejorar el idioma.',
        'tips': [
            'Combina formatos: 15 min de app/gramática + 15 min de escucha (podcast, serie).',
            'Anota 3 palabras nuevas al día y repásalas la semana siguiente.',
            'Habla en voz alta aunque sea sola — la producción oral es la que más cuesta.',
        ],
        'links': [_yt('practicar español para principiantes conversación')],
    },
    'Leer 20 min': {
        'description': 'Lectura diaria breve, de desarrollo profesional o personal.',
        'tips': [
            'Ten el libro siempre a mano (o el ebook abierto) para no perder el hábito por fricción.',
            'Anota una idea aplicable por sesión, no solo "leído".',
        ],
    },
    'Plan del día 10 min': {
        'description': 'Planificación breve al empezar el día: qué es lo importante hoy.',
        'tips': [
            'Elige máximo 3 prioridades reales del día, el resto es secundario.',
            'Hazlo siempre a la misma hora (nada más empezar) para que sea automático.',
        ],
    },
    'Meditación/Gratitud 10 min': {
        'description': 'Práctica breve de meditación o gratitud para empezar el día con calma.',
        'tips': [
            'Si eres principiante, empieza con respiración guiada de 5 minutos, no meditación silenciosa larga.',
            'Anota 3 cosas por las que estás agradecida — funciona incluso en días difíciles.',
        ],
        'links': [_yt('meditación guiada 10 minutos en español')],
    },

    # ── PERSONAL ──
    'Yoga / Estiramientos': {
        'description': 'Sesión de yoga o estiramientos para cuidar el cuerpo y bajar el nivel de tensión.',
        'tips': [
            'No hace falta esterilla especial ni ropa técnica para empezar — solo espacio y ropa cómoda.',
            'Prioriza estirar cuello, espalda y caderas si pasas muchas horas sentada.',
            'Respira lento y por la nariz durante los estiramientos; no fuerces hasta el dolor.',
            'Si vas a clases online, elige nivel principiante aunque lleves tiempo practicando en casa.',
        ],
        'links': [
            {'label': 'Yoga en 10 minutos para principiantes (MalovaElena, español)', 'url': 'https://www.youtube.com/watch?v=qTj9vti6Dw0'},
            {'label': 'Canal Xuan Lan Yoga (español)', 'url': 'https://www.youtube.com/xuanlanyoga'},
        ],
    },
    'Estiramiento': {
        'description': 'Sesión breve de estiramientos para aliviar tensión muscular.',
        'tips': [
            'Estira despacio, sin rebotes, manteniendo cada postura 20-30 segundos.',
            'Céntrate en la zona que más molesta ese día (cuello, lumbar, hombros).',
        ],
        'links': [_yt('estiramientos para aliviar dolor de espalda y cuello')],
    },
    'Paseo en la naturaleza': {
        'description': 'Paseo al aire libre, en entorno natural si es posible, para desconectar.',
        'tips': [
            'Deja el móvil en modo avión o guardado los primeros 10 minutos.',
            'Camina sin objetivo de "hacer ejercicio" — el objetivo aquí es desconectar, no rendir.',
        ],
    },
    'Paseo / Naturaleza': {
        'description': 'Tiempo al aire libre para despejar la mente.',
        'tips': [
            'Aunque sea un parque cercano cuenta — no hace falta ir lejos.',
            'Aprovecha para no mirar el móvil salvo para música o un podcast ligero.',
        ],
    },
    'Paseo al aire libre': {
        'description': 'Salir a caminar al aire libre como pausa activa del día.',
        'tips': [
            'Ideal a media mañana o después de comer para cortar el sedentarismo.',
            'Combínalo con una llamada personal (no de trabajo) si quieres aprovechar el tiempo.',
        ],
    },
    'Deporte al aire libre': {
        'description': 'Actividad física al aire libre: correr, bici, deporte con otras personas.',
        'tips': [
            'Si vienes de parar, empieza por sesiones cortas (20-25 min) para no lesionarte.',
            'Queda con alguien si puedes — el compromiso social ayuda a no cancelarlo.',
        ],
    },
    'Leer 1 hora': {
        'description': 'Sesión larga de lectura — buen momento para libros de fondo, no solo artículos rápidos.',
        'tips': [
            'Reserva un espacio sin notificaciones — el móvil en otra habitación si puedes.',
            'No fuerces terminar el libro si no te aporta; cambiar de lectura también vale.',
        ],
    },
    'Planificar semana': {
        'description': 'Organizar la semana completa: tareas, citas y tiempo personal.',
        'tips': [
            'Bloquea primero el tiempo personal/familiar, luego encaja el trabajo alrededor.',
            'Deja un margen libre (no lo llenes al 100%) para imprevistos.',
        ],
    },
    'Tiempo en familia': {
        'description': 'Tiempo dedicado a la familia, sin trabajo de por medio.',
        'tips': [
            'Guarda el móvil de verdad — no basta con "tenerlo en silencio" al lado.',
            'Elige una actividad compartida (juego, comida, paseo) en vez de "estar juntos" pasivamente.',
        ],
    },
    'Meditación / Gratitud': {
        'description': 'Práctica de meditación o gratitud para cuidar el estado de ánimo.',
        'tips': [
            'Si no sabes por dónde empezar, usa un audio guiado en vez de intentarlo en silencio total.',
            'Escribe 3 cosas buenas del día, por pequeñas que parezcan.',
        ],
        'links': [_yt('meditación guiada gratitud en español')],
    },
    'Cocina saludable': {
        'description': 'Preparar comida casera y saludable — también cuenta como cuidado personal.',
        'tips': [
            'Cocina en cantidad y guarda raciones — te quita presión los días de más trabajo.',
            'Prioriza verdura y proteína simple sobre recetas complicadas entre semana.',
        ],
    },
    'Tiempo personal': {
        'description': 'Tiempo libre sin agenda ni obligación, solo para ti.',
        'tips': [
            'No lo llenes de "tareas pendientes de casa" — eso sigue siendo trabajo.',
            'Elige algo que de verdad disfrutes, aunque parezca "improductivo".',
        ],
    },
    'Arte / Creatividad': {
        'description': 'Actividad creativa (dibujo, manualidades, música, escritura) sin fin comercial.',
        'tips': [
            'No busques que "salga bien" — el objetivo es el proceso, no el resultado.',
            'Ten materiales básicos siempre a mano para reducir la fricción de empezar.',
        ],
    },
    'Creatividad libre': {
        'description': 'Tiempo de creación libre, sin objetivo ni cliente de por medio.',
        'tips': [
            'Ponte un límite de tiempo corto (20-30 min) para no sentir que "debe" convertirse en algo grande.',
        ],
    },
    'Música / Arte': {
        'description': 'Disfrutar de música o arte como forma de descanso mental.',
        'tips': [
            'Escuchar activamente (sin hacer otra cosa a la vez) relaja más que de fondo.',
            'Prueba algo nuevo de vez en cuando, no solo lo de siempre.',
        ],
    },
    'Reflexión semanal': {
        'description': 'Parar a pensar cómo ha ido la semana, más allá de las tareas hechas.',
        'tips': [
            'Pregúntate: ¿qué me dio energía esta semana y qué me la quitó?',
            'Anota un ajuste pequeño para la semana que viene.',
        ],
    },
    'Diario personal': {
        'description': 'Escribir de forma libre sobre cómo te sientes o lo que ha pasado en el día.',
        'tips': [
            'No busques "escribir bien" — nadie más lo va a leer.',
            'Si no sabes por dónde empezar, escribe literalmente "hoy me siento..." y sigue desde ahí.',
        ],
    },
    'Escribir en el diario': {
        'description': 'Momento breve de escritura personal para procesar el día.',
        'tips': [
            'Hazlo siempre a la misma hora (ej. antes de dormir) para que se vuelva rutina.',
        ],
    },
    'Descanso consciente': {
        'description': 'Parar de forma intencional, sin pantallas, para recargar energía.',
        'tips': [
            'Elige una actividad sin pantalla (estirarte, mirar por la ventana, respirar).',
            'Pon una alarma si te cuesta parar — así no sientes que "pierdes tiempo".',
        ],
    },
    'Descanso profundo': {
        'description': 'Descanso real y largo (siesta, tarde libre) para recuperar energía de fondo.',
        'tips': [
            'Si es siesta, que sea corta (20-30 min) para no afectar el sueño nocturno.',
            'Evita revisar el móvil justo antes — cuesta mucho más desconectar de verdad.',
        ],
    },
    'Desconexión total': {
        'description': 'Bloque de tiempo sin trabajo ni pantallas, desconexión real.',
        'tips': [
            'Avisa antes si esperas mensajes importantes, así puedes desconectar sin culpa.',
            'Deja el móvil fuera de la habitación o en modo avión durante el bloque.',
        ],
    },
    'Evaluar aprendizajes': {
        'description': 'Revisar qué has aprendido en un periodo (semana, mes, proyecto).',
        'tips': [
            'Anota tanto aciertos como errores — los errores enseñan más si los registras.',
            'Convierte el aprendizaje en una regla concreta para el futuro, no solo una nota.',
        ],
    },
    'Escribir metas': {
        'description': 'Definir o revisar tus metas personales o profesionales por escrito.',
        'tips': [
            'Escribe metas medibles con fecha, no deseos abstractos.',
            'Revisa las metas antiguas antes de escribir nuevas — algunas quizá ya no apliquen.',
        ],
    },
    'Visualización': {
        'description': 'Ejercicio breve de visualización de objetivos o de cómo quieres que salga algo importante.',
        'tips': [
            'Sé específica: visualiza una escena concreta, no una idea vaga de "éxito".',
            'Combínalo con respiración lenta para que sea más efectivo.',
        ],
        'links': [_yt('meditación de visualización de objetivos en español')],
    },

    # ── CIERRE ──
    'Celebrar logros': {
        'description': 'Reconocer de forma consciente lo que has conseguido en el mes.',
        'tips': [
            'Haz una lista concreta de logros, aunque sean pequeños — no solo "fue un buen mes".',
            'Celebra de una forma real (no solo mental): cuéntaselo a alguien, date un capricho.',
        ],
    },
    'Gratitud': {
        'description': 'Momento de gratitud consciente al cerrar el mes o el día.',
        'tips': [
            'Sé específica: no "estoy agradecida por mi negocio", sino por qué momento concreto.',
        ],
    },
    'Plan fin de semana': {
        'description': 'Planificación breve del fin de semana para que no se diluya en pantallas o trabajo.',
        'tips': [
            'Decide de antemano 1 cosa que quieres hacer, así no llega el domingo sin haber pasado nada.',
            'Define también cuándo NO vas a trabajar, no solo cuándo sí.',
        ],
    },
}
