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
