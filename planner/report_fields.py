"""Report form schema per task category — which fields to show when reporting
progress on a calendar entry, depending on its category.

Each field is [key, label, type, options?]. Supported types: text, textarea,
number, url, select (needs an options list).
"""

REPORT_FIELDS = {
    'ventas': [
        ['contacto', 'Empresa / persona de contacto', 'text'],
        ['resultado', 'Resultado', 'select', ['Positivo', 'Neutro', 'Sin respuesta']],
        ['siguiente_paso', 'Siguiente paso', 'text'],
    ],
    'contenido': [
        ['enlace', 'Enlace publicado', 'url'],
        ['alcance', 'Alcance / vistas', 'number'],
        ['notas', 'Notas', 'textarea'],
    ],
    'estrategia': [
        ['resumen', 'Resumen', 'textarea'],
        ['decision', 'Decisión tomada', 'text'],
    ],
    'finanzas': [
        ['importe', 'Importe (€)', 'number'],
        ['concepto', 'Concepto', 'text'],
    ],
    'perfil': [
        ['notas', 'Notas', 'textarea'],
    ],
    'personal': [
        ['notas', 'Notas', 'textarea'],
    ],
    'habito': [
        ['minutos', 'Minutos dedicados', 'number'],
        ['notas', 'Notas', 'textarea'],
    ],
    'cierre': [
        ['notas', 'Notas', 'textarea'],
    ],
}

CATEGORY_LABELS = dict([
    ('ventas', 'Ventas y prospección'),
    ('contenido', 'Contenido y marketing'),
    ('estrategia', 'Estrategia y negocio'),
    ('finanzas', 'Finanzas'),
    ('perfil', 'Marca personal'),
    ('personal', 'Día personal'),
    ('habito', 'Hábito diario'),
    ('cierre', 'Cierre de mes'),
])
