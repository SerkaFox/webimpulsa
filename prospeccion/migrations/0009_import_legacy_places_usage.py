# Importa los contadores diarios de la tabla PlacesApiUsage (el mecanismo
# ANTERIOR a este control por tipo de request) como request_type
# 'legacy_unknown' — nunca se inventa qué proporción de cada día era Text
# Search vs Nearby Search, porque el dato real no existe.
#
# No se borra PlacesApiUsage (se mantiene tal cual, ver comentario en
# models.py). Esta migración es aditiva y reversible: al revertir, borra
# únicamente lo que ella misma creó (request_type='legacy_unknown').
from datetime import datetime, time as dtime
from zoneinfo import ZoneInfo

from django.db import migrations

_MADRID_TZ = ZoneInfo('Europe/Madrid')
_LA_TZ = ZoneInfo('America/Los_Angeles')
_LEGACY_TYPE = 'legacy_unknown'


def _billing_month_for_date(d):
    # Mismo mediodía usado como instante representativo del día (no se
    # conserva la hora real de cada llamada individual en el dato viejo).
    local_noon = datetime.combine(d, dtime(12, 0), tzinfo=_MADRID_TZ)
    return local_noon.astimezone(_LA_TZ).strftime('%Y-%m'), local_noon


def import_legacy_usage(apps, schema_editor):
    PlacesApiUsage = apps.get_model('prospeccion', 'PlacesApiUsage')
    PlacesApiMonthlyCounter = apps.get_model('prospeccion', 'PlacesApiMonthlyCounter')
    PlacesApiRequestLog = apps.get_model('prospeccion', 'PlacesApiRequestLog')

    for row in PlacesApiUsage.objects.all():
        if row.count <= 0:
            continue
        billing_month, moment = _billing_month_for_date(row.date)

        counter, _created = PlacesApiMonthlyCounter.objects.get_or_create(
            billing_month=billing_month, request_type=_LEGACY_TYPE,
        )
        counter.reserved_count += row.count
        counter.success_count += row.count  # dato viejo no distinguía éxito/error
        counter.save(update_fields=['reserved_count', 'success_count'])

        logs = [
            PlacesApiRequestLog(
                created_at=moment, billing_month=billing_month, request_type=_LEGACY_TYPE,
                endpoint='', success=True, error_type='',
            )
            for _ in range(row.count)
        ]
        PlacesApiRequestLog.objects.bulk_create(logs)


def remove_legacy_usage(apps, schema_editor):
    PlacesApiMonthlyCounter = apps.get_model('prospeccion', 'PlacesApiMonthlyCounter')
    PlacesApiRequestLog = apps.get_model('prospeccion', 'PlacesApiRequestLog')
    PlacesApiRequestLog.objects.filter(request_type=_LEGACY_TYPE).delete()
    PlacesApiMonthlyCounter.objects.filter(request_type=_LEGACY_TYPE).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('prospeccion', '0008_places_usage_control'),
    ]

    operations = [
        migrations.RunPython(import_legacy_usage, remove_legacy_usage),
    ]
