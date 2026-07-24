"""Traduce los `fix_ids` de un ChequeoAudit a servicios concretos y con precio
del catálogo ya existente (`crm.proposal_content`), en vez de un mensaje
genérico de "necesitas mejorar tu presencia digital". La pregunta `mobile_page`
("¿tienes un canal propio que funcione bien en el móvil?") es el servicio base
de WebImpulsa, no un extra — se marca aparte (`needs_core_site`) para no
ofrecer una web a quien ya la tiene ni mezclarla con la lista de add-ons.
"""
from crm.proposal_content import EXTRAS_DESCRIPTIONS, EXTRAS_PRICES, HOURS_PACKAGES

QUESTION_RECOMMENDATIONS = {
    'gbp_accuracy':          {'extra': 'Ficha en Google Maps'},
    'mobile_page':           {'core': True},
    'catalog_visible':       {'extra': 'Menú/catálogo digital'},
    'one_tap_contact':       {'extra': 'Botón de WhatsApp'},
    'main_action_no_wait':   {'extra_by_sector': {
        'bar': 'Pedidos online',
        'tienda': 'Pedidos online',
        '_default': 'Citas y reservas online',
    }},
    'messages_lost':         {'extra': 'Panel para tu equipo'},
    'auto_confirmation':     {'extra': 'Avisos antes de cada cita'},
    'reviews_uptodate':      {'hours_package': 'Bolsa 5 horas'},
    'centralized_records':   {'extra': 'Panel para tu equipo'},
    'repetitive_tasks':      {'extra': 'Asistente automático 24h'},
    'brings_back_customers': {'hours_package': 'Bolsa 5 horas'},
}


def _extra_name_for(qid, sector, rule):
    if 'extra' in rule:
        return rule['extra']
    if 'extra_by_sector' in rule:
        by_sector = rule['extra_by_sector']
        return by_sector.get(sector, by_sector['_default'])
    if 'hours_package' in rule:
        return rule['hours_package']
    return None


def build_recommendations(sector, fix_ids):
    """Devuelve {'needs_core_site': bool, 'items': [{label, price, description}],
    'estimated_total': int} a partir de los fix_ids reales de un chequeo —
    nunca a partir de un texto fijo, y nunca repite el mismo servicio dos veces
    aunque varias preguntas apunten a él."""
    needs_core_site = False
    seen = set()
    items = []

    for qid in fix_ids:
        rule = QUESTION_RECOMMENDATIONS.get(qid)
        if not rule:
            continue
        if rule.get('core'):
            needs_core_site = True
            continue
        name = _extra_name_for(qid, sector, rule)
        if not name or name in seen:
            continue
        seen.add(name)
        price = EXTRAS_PRICES.get(name) or HOURS_PACKAGES.get(name)
        if price is None:
            continue
        items.append({
            'label': name,
            'price': price,
            'description': EXTRAS_DESCRIPTIONS.get(name, ''),
        })

    return {
        'needs_core_site': needs_core_site,
        'items': items,
        'estimated_total': sum(it['price'] for it in items),
    }
