"""Draft outreach messages for Tania to review and send herself via her own
WhatsApp — this module only generates text, it never sends anything, so the
GDPR/LSSICE consent gating that applies to the automated report-delivery
bridge (see BusinessContact.consent_commercial_contact) does not apply here.

The whole point is to reduce the mental friction of a cold approach: every
variant leads with a free, no-obligation offer instead of an ask, so it reads
as "aquí tienes algo gratis" rather than "cómprame algo".
"""

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


def build_opener_variants(prospect):
    """Returns a list of 2-3 short WhatsApp opener message strings, ordered
    from most-specific (uses a known real signal about the business) to most
    generic (used when we don't know anything yet)."""
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

    variants.append(
        f'Hola! Soy Tania, ayudo a {sector_word}s de la zona a que los encuentren y contacten más fácil '
        f'por internet. Hago un chequeo gratis de 2 minutos, sin compromiso — ¿os interesaría ver cómo '
        f'os ve un cliente que os busca en Google?'
    )

    return variants[:3]


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
