from django.db import migrations

# Todos los puntos de tareas recogidos del calendario impreso "TATIANA BE
# SUCCESS CALENDAR" (julio 2026), agrupados por categoría para poder elegir
# desde una única lista al rellenar cualquier día.
CATALOG = [
    # (title, category, default_points)

    # Ventas y prospección
    ("Analizar clientes actuales", "ventas", 40),
    ("Investigar a 3 empresas", "ventas", 40),
    ("Contactar 2 empresas", "ventas", 40),
    ("Presentación comercial", "ventas", 40),
    ("Propuesta de valor clara", "ventas", 40),
    ("Enviar 3 propuestas", "ventas", 40),
    ("Seguimiento clientes", "ventas", 40),
    ("Reunión estratégica", "ventas", 40),
    ("Detectar necesidades", "ventas", 40),
    ("Preparar propuesta", "ventas", 40),
    ("Establecer precios claros", "ventas", 40),
    ("Llamadas de seguimiento", "ventas", 40),
    ("Crear alianza estratégica", "ventas", 40),
    ("Contactar 3 potenciales", "ventas", 40),
    ("Analizar competencia", "ventas", 40),
    ("Networking online", "ventas", 40),
    ("Propuesta de colaboración", "ventas", 40),
    ("Negociar proyectos", "ventas", 40),
    ("Cerrar acuerdos", "ventas", 40),
    ("Detectar oportunidades", "ventas", 40),
    ("Llamadas de prospección", "ventas", 40),
    ("Propuesta personalizada", "ventas", 40),
    ("Delegar tareas", "ventas", 40),
    ("Cerrar proyecto", "ventas", 40),
    ("Onboarding cliente", "ventas", 40),
    ("Evaluar resultados", "ventas", 40),
    ("Analizar resultados", "ventas", 40),
    ("Definir próximos pasos", "ventas", 40),

    # Contenido y marketing
    ("Publicar post en LinkedIn", "contenido", 40),
    ("Crear contenido de valor", "contenido", 40),
    ("Publicar en redes sociales", "contenido", 40),
    ("Email marketing (envío)", "contenido", 40),
    ("Analizar métricas", "contenido", 40),
    ("Testimonios / Pruebas", "contenido", 40),
    ("Mejorar landing page", "contenido", 40),
    ("Crear contenido (vídeo)", "contenido", 40),
    ("Crear guía / Recurso", "contenido", 40),
    ("Publicar en redes", "contenido", 40),
    ("Email marketing (valor)", "contenido", 40),
    ("Taller / Formación", "contenido", 40),
    ("Preparar contenido", "contenido", 40),
    ("Publicar en LinkedIn", "contenido", 40),
    ("Crear estudio de caso", "contenido", 40),
    ("Publicar en blog/LinkedIn", "contenido", 40),
    ("Mejorar portfolio", "contenido", 40),
    ("Webinar / Directo", "contenido", 40),
    ("Crear plantilla / Recurso", "contenido", 40),
    ("Publicar testimonio", "contenido", 40),
    ("Captar leads en LinkedIn", "contenido", 40),
    ("Publicar caso de éxito", "contenido", 40),

    # Estrategia y negocio
    ("Definir objetivos semanales", "estrategia", 40),
    ("Crear oferta irresistible", "estrategia", 40),
    ("Estandarizar servicio 1", "estrategia", 40),
    ("Mejorar web (1 ajuste)", "estrategia", 40),
    ("Mejorar automatizaciones", "estrategia", 40),
    ("Optimizar procesos", "estrategia", 40),
    ("Mejorar procesos internos", "estrategia", 40),
    ("Plan de crecimiento", "estrategia", 40),
    ("Optimizar servicios", "estrategia", 40),
    ("Crear plan de agosto", "estrategia", 40),
    ("Preparar campañas", "estrategia", 40),
    ("Automatizar procesos", "estrategia", 40),
    ("Evaluación mensual", "estrategia", 40),
    ("Presentación online", "estrategia", 40),

    # Finanzas
    ("Orden financiero", "finanzas", 40),
    ("Facturación / Finanzas", "finanzas", 40),
    ("Revisión financiera", "finanzas", 40),
    ("Facturación / Cobros", "finanzas", 40),
    ("Ajustar precios", "finanzas", 40),

    # Marca personal
    ("Optimizar perfil profesional", "perfil", 40),

    # Día personal / fin de semana
    ("Paseo en la naturaleza", "personal", 0),
    ("Leer 1 hora", "personal", 0),
    ("Planificar semana", "personal", 0),
    ("Tiempo en familia", "personal", 0),
    ("Meditación / Gratitud", "personal", 0),
    ("Yoga / Estiramientos", "personal", 0),
    ("Cocina saludable", "personal", 0),
    ("Deporte al aire libre", "personal", 0),
    ("Tiempo personal", "personal", 0),
    ("Paseo / Naturaleza", "personal", 0),
    ("Arte / Creatividad", "personal", 0),
    ("Reflexión semanal", "personal", 0),
    ("Diario personal", "personal", 0),
    ("Creatividad libre", "personal", 0),
    ("Descanso consciente", "personal", 0),
    ("Desconexión total", "personal", 0),
    ("Paseo al aire libre", "personal", 0),
    ("Escribir en el diario", "personal", 0),
    ("Música / Arte", "personal", 0),
    ("Descanso profundo", "personal", 0),
    ("Estiramiento", "personal", 0),
    ("Evaluar aprendizajes", "personal", 0),
    ("Escribir metas", "personal", 0),
    ("Visualización", "personal", 0),

    # Hábitos diarios obligatorios
    ("Ejercicio físico 20 min", "habito", 0),
    ("Castellano 30 min", "habito", 0),
    ("Leer 20 min", "habito", 0),
    ("Plan del día 10 min", "habito", 0),
    ("Meditación/Gratitud 10 min", "habito", 0),

    # Cierre de mes
    ("Celebrar logros", "cierre", 40),
    ("Gratitud", "cierre", 40),
    ("Plan fin de semana", "cierre", 40),
]


def seed_catalog(apps, schema_editor):
    TaskCatalogItem = apps.get_model('planner', 'TaskCatalogItem')
    for order, (title, category, points) in enumerate(CATALOG):
        TaskCatalogItem.objects.update_or_create(
            title=title,
            defaults={'category': category, 'default_points': points, 'order': order},
        )


def unseed_catalog(apps, schema_editor):
    TaskCatalogItem = apps.get_model('planner', 'TaskCatalogItem')
    titles = [title for title, _, _ in CATALOG]
    TaskCatalogItem.objects.filter(title__in=titles).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('planner', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed_catalog, unseed_catalog),
    ]
