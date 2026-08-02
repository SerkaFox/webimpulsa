"""Draft outreach messages for Tania to review and send herself via her own
WhatsApp — this module only generates text, it never sends anything, so the
GDPR/LSSICE consent gating that applies to the automated report-delivery
bridge (see BusinessContact.consent_commercial_contact) does not apply here.

The whole point is to reduce the mental friction of a cold approach: every
variant leads with a free, no-obligation offer instead of an ask, so it reads
as "aquí tienes algo gratis" rather than "cómprame algo".
"""
import random
from datetime import date

SECTOR_SHORT_NAMES = {
    'salon': 'salón',
    'bar': 'bar o restaurante',
    'taller': 'taller',
    'academia': 'academia',
    'clinica': 'clínica',
    'tienda': 'tienda',
    'inmobiliaria': 'negocio',
    'otro': 'negocio',
}


def _sector_word(sector):
    return SECTOR_SHORT_NAMES.get(sector, 'negocio')


# Pool de aperturas genéricas (no dependen de una señal concreta del
# negocio) — variadas a propósito en tono y estructura para que, aunque se
# repita el chequeo gratis como núcleo, nunca suenen a la misma plantilla
# copiada. Se elige un subconjunto "fresco" cada día (ver _pick_pool), no
# siempre las mismas 3-4 de arriba del todo.
GENERIC_POOL = [
    'Hola! Soy Tania, ayudo a {sector_word}s de la zona a que los encuentren y contacten más fácil por '
    'internet. Hago un chequeo gratis de 2 minutos, sin compromiso — ¿os interesaría ver cómo os ve un '
    'cliente que os busca en Google?',
    'Hola! Soy Tania — estoy haciendo chequeos digitales gratuitos para negocios de la zona, como parte de '
    'un proyecto para ayudar a que el comercio local se digitalice mejor. Me gustaría hacerte uno a {name} '
    'también, sin compromiso — ¿te interesa ver cómo te encuentra hoy un cliente que te busca en Google?',
    'Hola! Soy Tania, de CreaGanaWeb. ¿Tienes 2 minutos? Hago un chequeo gratis de cómo os encuentra un '
    'cliente que os busca en Google — sin compromiso, solo para que veas si hay algo fácil de mejorar.',
    'Hola! Vi {name} y me gustó cómo lleváis el negocio. Ayudo a {sector_word}s con su presencia online — '
    '¿te interesa un chequeo gratis de 2 minutos para ver cómo os encuentra un cliente en Google?',
    'Hola! Soy Tania. Trabajo con varios negocios de la zona ayudándoles a que los encuentren mejor por '
    'internet. ¿Te importa si te hago un chequeo rápido y gratuito a {name}, sin compromiso ninguno?',
    'Hola! ¿Cómo va el día en {name}? Soy Tania, hago chequeos gratuitos de presencia digital para negocios '
    'locales — 2 minutos, sin compromiso. ¿Te interesa ver qué tal os ve un cliente que os busca en Google?',
    'Hola! Soy Tania de CreaGanaWeb. Una pregunta rápida: ¿alguna vez has buscado tu propio negocio en '
    'Google para ver cómo aparece? Te puedo hacer ese chequeo gratis en 2 minutos, sin compromiso.',
    'Hola! Ayudo a {sector_word}s de la zona a mejorar su presencia en internet — cosas como aparecer en '
    'Google, tener botón de WhatsApp o reservas online. ¿Te hago un chequeo gratis de {name}, sin '
    'compromiso, para ver qué tal está?',
    'Hola! Soy Tania. Ya he ayudado a varios negocios de por aquí a mejorar cómo los encuentran los '
    'clientes online. ¿Te interesaría el mismo chequeo gratis para {name}? Son solo 2 minutos.',
    'Hola! Soy Tania de CreaGanaWeb — hago un chequeo digital gratuito, sin compromiso, que muestra cómo os '
    'encuentra hoy un cliente que os busca en Google. ¿Te interesa verlo para {name}?',
    'Hola! Vi que {name} está en la zona y quería preguntarte algo rápido: ¿sabes cómo aparece tu negocio '
    'cuando alguien lo busca en Google? Te lo puedo comprobar gratis, sin compromiso.',
    'Hola! Soy Tania — ayudo a negocios como el tuyo a que los clientes los encuentren y contacten más '
    'fácil por internet. Chequeo gratuito de 2 minutos, sin compromiso. ¿Te interesa para {name}?',
    'Hola! ¿Tienes un minuto? Soy Tania, hago chequeos gratis para ver si un cliente puede encontrar, '
    'entender y contactar con {name} fácilmente por internet. Sin compromiso, solo para que lo veas.',
    'Hola! Soy Tania de CreaGanaWeb. Muchos {sector_word}s de la zona no saben cómo los ve realmente un '
    'cliente en Google — te puedo hacer ese chequeo gratis para {name}, 2 minutos, sin compromiso.',
    'Hola! Soy Tania. Si tienes un momento, te hago gratis un chequeo de cómo os encuentra un cliente que '
    'os busca en Google — sin compromiso, y si todo está bien no hace falta cambiar nada.',
    'Hola! Me llamo Tania y ayudo a negocios locales con su presencia digital. Curiosidad: ¿tienes ficha en '
    'Google Maps actualizada? Te reviso {name} gratis en 2 minutos, sin compromiso.',
    'Hola! Soy Tania de CreaGanaWeb. Suelo ayudar a {sector_word}s a que no pierdan clientes por no '
    'aparecer bien en internet. ¿Te interesa un chequeo gratuito de {name}, sin compromiso?',
    'Hola! Soy Tania — trabajo digitalizando negocios locales. Antes de nada, te ofrezco algo gratis: un '
    'chequeo de 2 minutos de cómo os ve un cliente que os busca online. ¿Te viene bien?',
    'Hola! ¿Qué tal? Soy Tania, ayudo a negocios de la zona con su presencia en internet. Te puedo hacer un '
    'chequeo gratuito de {name}, sin compromiso, para ver si hay algo fácil de mejorar.',
    'Hola! Soy Tania de CreaGanaWeb. Si te interesa, te hago un chequeo digital gratis y sin compromiso — '
    'solo para ver cómo aparece {name} cuando alguien lo busca en Google.',
    'Hola! Vi tu negocio y me gustaría ofrecerte algo gratis: un chequeo de 2 minutos de tu presencia '
    'online. Sin compromiso — solo para que sepas si un cliente os encuentra bien en Google.',
    'Hola! Soy Tania. Ayudo a negocios como {name} a mejorar cómo los encuentran los clientes por internet '
    '— reservas, WhatsApp, Google Maps. ¿Te hago el chequeo gratis, sin compromiso?',
    'Hola! Soy Tania de CreaGanaWeb. Pregunta rápida: si un cliente nuevo busca «{sector_word} cerca de mí», '
    '¿aparece {name}? Te lo compruebo gratis en 2 minutos, sin compromiso.',
    'Hola! Soy Tania — hago chequeos digitales gratuitos para negocios locales, sin ningún compromiso. Solo '
    'te cuento qué veo, tú decides si quieres hacer algo con ello. ¿Te interesa para {name}?',
    'Hola! ¿Cómo va todo por {name}? Soy Tania, ayudo a negocios de la zona con su presencia digital — te '
    'ofrezco un chequeo gratuito, 2 minutos, sin compromiso, a ver qué tal os ve un cliente en Google.',
    'Hola! Soy Tania de CreaGanaWeb. Sin rollos: te hago gratis un chequeo de 2 minutos de tu presencia '
    'online, sin compromiso. Si está todo bien, perfecto, y si no, te cuento qué mejorar.',
    'Hola! Trabajo ayudando a {sector_word}s locales a estar mejor en internet. Te ofrezco un chequeo '
    'digital gratuito para {name}, sin compromiso — ¿te interesa ver el resultado?',
    'Hola! Soy Tania. Muchos negocios pierden clientes solo por cosas pequeñas en su presencia online — te '
    'hago un chequeo gratis de {name} para ver si es tu caso, sin compromiso.',
    'Hola! Soy Tania de CreaGanaWeb, trabajo con negocios de la zona. ¿Te gustaría saber gratis cómo os '
    'encuentra hoy un cliente que os busca en internet? Sin compromiso, 2 minutos.',
    'Hola! Vi {name} y pensé en preguntarte: ¿tenéis manera fácil de que un cliente os escriba por '
    'WhatsApp desde vuestra web o ficha de Google? Te lo compruebo gratis, sin compromiso.',
    'Hola! Soy Tania de CreaGanaWeb. ¿Alguna vez un cliente te ha dicho «no os encontraba»? Te hago un '
    'chequeo gratis de {name} para ver si hay algo fácil de arreglar — sin compromiso.',
    'Hola! Ayudo a {sector_word}s a que su negocio se vea profesional desde el móvil, que es como mira la '
    'mayoría de la gente hoy. ¿Te reviso {name} gratis, sin compromiso, para ver qué tal está?',
    'Hola! Soy Tania. No vendo nada por mensaje — solo te ofrezco un chequeo gratuito y sin compromiso de '
    'cómo os ve un cliente que os busca en Google. ¿Te interesa para {name}?',
    'Hola! Soy Tania de CreaGanaWeb. Si tienes 2 minutos algún día, te hago un chequeo gratis de {name} — '
    'sin compromiso, solo información útil sobre vuestra presencia online.',
    'Hola! Vi que estáis en la zona y me hizo ilusión escribiros — ayudo a negocios locales con su '
    'presencia digital. ¿Te interesa un chequeo gratuito y sin compromiso de {name}?',
    'Hola! Soy Tania. Trabajo puerta a puerta y online ayudando a {sector_word}s a mejorar cómo los '
    'encuentran los clientes. Chequeo gratis, sin compromiso — ¿te viene bien para {name}?',
    'Hola! Soy Tania de CreaGanaWeb. Si {name} tiene catálogo o carta, ¿está actualizado online? Te '
    'compruebo eso y más gratis en 2 minutos, sin compromiso.',
    'Hola! Ayudo a negocios locales a recuperar clientes que se pierden por detalles pequeños en su '
    'presencia online. Te hago el chequeo gratis para {name}, sin compromiso — ¿te interesa?',
    'Hola! Soy Tania. Igual ya tenéis todo perfecto, pero por si acaso: te ofrezco un chequeo digital '
    'gratuito y sin compromiso para {name}, a ver cómo os ve un cliente nuevo.',
    'Hola! Soy Tania de CreaGanaWeb, ayudo a negocios de la zona a digitalizarse un poco más cada mes. '
    '¿Empezamos con un chequeo gratis y sin compromiso de {name}?',
    'Hola! Buenas — soy Tania. ¿Te interesaría saber, gratis y sin compromiso, cómo aparece {name} cuando '
    'alguien lo busca en el móvil? Son 2 minutos.',
    'Hola! Soy Tania de CreaGanaWeb. Últimamente ayudo a varios {sector_word}s de la zona con su web y su '
    'ficha de Google. ¿Te apetece un chequeo gratis y sin compromiso para {name}?',
    'Hola! Soy Tania. Sin ánimo de molestar: te dejo la opción de un chequeo digital gratis y sin '
    'compromiso para {name}, por si te viene bien saber cómo os ve un cliente nuevo.',
    'Hola! ¿Qué tal, {name}? Soy Tania, ayudo a negocios de la zona a que no se les escape ningún cliente '
    'por internet. Chequeo gratis, sin compromiso — ¿te interesa?',
    'Hola! Soy Tania de CreaGanaWeb. A veces un detalle pequeño (una foto, un horario mal puesto) hace que '
    'se pierdan clientes. Te lo reviso gratis en {name}, sin compromiso.',
    'Hola! Soy Tania, trabajo con negocios locales. Si algún día te apetece, te hago un chequeo gratuito de '
    '{name} sin compromiso — solo para que sepas cómo estáis online.',
    'Hola! Buenas, soy Tania de CreaGanaWeb. ¿Te va bien si te hago un chequeo rápido y gratis de la '
    'presencia digital de {name}? Sin compromiso, tú decides después qué hacer con la info.',
]

# Pool de aperturas "señal" — mismo estilo, pero orientadas a un dato
# concreto que se puede mencionar aunque no venga de un has_website/score.
SOFT_HOOK_POOL = [
    'Hola! Soy Tania. Estaba mirando negocios de {sector_word} por la zona y quería preguntarte algo '
    'rápido: ¿tenéis reservas o citas online, o la gente tiene que llamar? Te hago un chequeo gratis, sin '
    'compromiso, para ver qué tal está {name}.',
    'Hola! Soy Tania de CreaGanaWeb. ¿{name} tiene ficha en Google Maps con horario y fotos actualizadas? '
    'Te lo reviso gratis en 2 minutos, sin compromiso — es de lo primero que mira un cliente nuevo.',
    'Hola! Soy Tania — ayudo a negocios locales a no perder mensajes de clientes. ¿Sueles perder algún '
    'WhatsApp o llamada por no estar disponible? Te hago un chequeo gratis de {name}, sin compromiso.',
]


def _pick_pool(prospect, pool, k):
    """Selección determinista-pero-variable: misma empresa + mismo día ->
    mismo subconjunto (estable si recarga la página), día distinto -> otro
    subconjunto (se siente "fresco" sin depender de guardar historial)."""
    seed = f'{prospect.pk}-{date.today().isoformat()}'
    rng = random.Random(seed)
    return rng.sample(pool, min(k, len(pool)))


def build_opener_variants(prospect):
    """Returns a short list of WhatsApp opener message strings: primero las
    que usan una señal real y conocida del negocio (sin web, sin botón de
    WhatsApp, score bajo), luego 3-4 "frescas" elegidas del pool de ~40+
    variantes genéricas — para que cada día se vea algo distinto sin perder
    la opción de ciclar entre varias con el botón "Otra opción"."""
    name = prospect.name.strip()
    sector_word = _sector_word(prospect.sector)
    variants = []

    if prospect.has_website is False or not prospect.website:
        variants.append(
            f'Hola! Soy Tania, ayudo a {sector_word}s a que los clientes los encuentren mejor en internet. '
            f'Vi que {name} todavía no tiene página web — os puedo hacer un chequeo gratis de 2 minutos '
            f'para ver cómo os encuentra hoy un cliente que os busca en Google. Sin compromiso, ¿os interesa?'
        )

    if prospect.has_whatsapp_cta is False and (prospect.has_website or prospect.website):
        variants.append(
            f'Hola! Soy Tania, ayudo a negocios locales con su presencia online. Vi la web de {name} '
            f'y me falta encontrar un botón de WhatsApp para escribiros directamente — muchos clientes '
            f'prefieren eso a llamar. ¿Os hago un chequeo gratis de 2 minutos para ver qué más se puede mejorar?'
        )

    if prospect.current_score is not None and prospect.current_score < 70:
        variants.append(
            f'Hola! Soy Tania de CreaGanaWeb. Le hice un chequeo rápido y gratuito a {name} de cómo se ve '
            f'online — hay un par de cosas fáciles de mejorar. ¿Te va bien si te cuento qué encontré? '
            f'Sin compromiso ninguno.'
        )

    fresh = _pick_pool(prospect, GENERIC_POOL + SOFT_HOOK_POOL, k=4)
    for template in fresh:
        variants.append(template.format(name=name, sector_word=sector_word))

    return variants


def build_referral_message(prospect):
    """Warm, low-pressure referral request for an already-won client — asking
    an existing happy client for a recommendation is psychologically much
    easier than cold-approaching a stranger, so this is meant as the easy
    second lever, not a replacement for the opener messages."""
    name = prospect.name.strip()
    return (
        f'Hola! Soy Tania, de CreaGanaWeb — un placer haber trabajado con {name}. '
        f'Si conoces a algún otro negocio de la zona al que le vendría bien mejorar su presencia online, '
        f'le puedo hacer el mismo chequeo gratuito que os hice a vosotros, sin compromiso. '
        f'¡Muchas gracias de antemano!'
    )
