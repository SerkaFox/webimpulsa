from .models import BusinessProspect

# Color del marcador = etapa de trabajo (sales_status), nunca un juicio sobre
# la empresa. El score se muestra aparte, como número o anillo, nunca como
# color del marcador.
SALES_STATUS_COLORS = {
    BusinessProspect.SALES_DISCOVERED: '#8a94a6',       # gris
    BusinessProspect.SALES_PRE_AUDITED: '#2563eb',      # azul
    BusinessProspect.SALES_CONTACTED: '#eab308',        # amarillo
    BusinessProspect.SALES_AUDITED: '#f97316',          # naranja
    BusinessProspect.SALES_PRESUPUESTO: '#7c3aed',      # morado
    BusinessProspect.SALES_WON: '#16a34a',              # verde
    BusinessProspect.SALES_LOST: '#dc2626',             # rojo
    BusinessProspect.SALES_DO_NOT_CONTACT: '#7f1d1d',   # rojo oscuro
    BusinessProspect.SALES_ARCHIVED: '#111827',         # negro
}

# Insignias del mapa PÚBLICO — siempre positivas, calculadas al vuelo desde
# el último ChequeoAudit CONFIRMADO (nunca desde uno preliminar/sin
# confirmar). Nunca se guardan como estado aparte, para que sea imposible
# enseñar un dato no confirmado o negativo por construcción.
PUBLIC_BADGES = [
    {'key': 'info_verificada',   'label': 'Información verificada',  'question_id': 'gbp_accuracy'},
    {'key': 'contacto_facil',    'label': 'Contacto fácil',          'question_id': 'one_tap_contact'},
    {'key': 'reserva_rapida',    'label': 'Reserva/pedido rápido',   'question_id': 'main_action_no_wait'},
    {'key': 'menu_online',       'label': 'Menú/servicios online',   'question_id': 'catalog_visible'},
    {'key': 'respuesta_auto',    'label': 'Respuesta automatizada',  'question_id': 'auto_confirmation'},
]


def compute_public_badges(prospect, audit):
    """Insignias positivas para el mapa público. `audit` debe ser el último
    ChequeoAudit con stage='confirmado' de este prospecto, o None."""
    if not audit:
        return []
    good = set(audit.good_ids or [])
    badges = [b for b in PUBLIC_BADGES if b['question_id'] in good]
    if prospect.whatsapp:
        badges.append({'key': 'whatsapp_disponible', 'label': 'WhatsApp disponible', 'question_id': None})
    return badges
